"""Replay historical development features. Never opens OOT/blind CSVs or fits models.

This produces a candidate asset, not parity or publication approval. Original
development observation membership and labels are retained for reconciliation.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

SOURCE_SHA = 'bbf6b1a96869721ad00ad54f843232076fba50f658f0b306ba4e46ab21666231'
REFERENCE_SHA = 'be20bc3e4ae0cb94e1a70a2efeef2c0e96e3dd70f46ed6c90675ae019cb85d84'
FEATURES = ['service_tenure_days', 'arpu_sgd', 'usage_data_mb_sum_30d',
            'usage_data_mb_sum_prev30d', 'usage_data_mb_delta_30d_vs_prev30d',
            'usage_active_days_count_30d', 'billing_overdue_amount_sgd',
            'billing_payment_failure_count_90d', 'care_complaint_count_30d',
            'care_repeat_contact_count_30d', 'network_incident_count_30d',
            'network_degraded_minutes_30d', 'digital_active_days_count_30d',
            'product_change_count_90d', 'contract_remaining_days']
TABLES = {
    'usage_event': ['service_instance_id', 'usage_type', 'usage_unit', 'usage_quantity', 'event_ts'],
    'invoice': ['customer_id', 'invoice_amount', 'invoice_date'],
    'invoice_balance_history': ['customer_id', 'invoice_id', 'balance_history_id', 'outstanding_amount', 'transaction_ts'],
    'payment_transaction': ['customer_id', 'payment_status', 'transaction_ts'],
    'complaint': ['customer_id', 'submitted_ts'],
    'customer_interaction': ['customer_id', 'started_ts'],
    'service_impact_event': ['service_instance_id', 'detected_ts', 'resolved_ts'],
    'digital_session': ['customer_id', 'started_ts'],
    'product_order': ['service_instance_id', 'order_type', 'submitted_ts'],
    'contract_detail': ['service_instance_id', 'contract_id', 'contract_end_date', 'updated_ts'],
}
FORBIDDEN = ['private_custodian_only', 'synthetic_ground_truth', 'blind_truth',
             'latent_true_churn_probability', 'private_synthetic_churn_construction']


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def available(df, t0, contract=False):
    """Missing creation/ingestion time fails closed; future contract updates excluded."""
    mask = df.created_ts.notna() & df.ingested_ts.notna()
    mask &= df.created_ts.le(t0) & df.ingested_ts.le(t0)
    if contract:
        mask &= df.updated_ts.isna() | df.updated_ts.le(t0)
    return df.loc[mask].copy()


def window(df, ts, t0, days, end=None):
    end = t0 if end is None else end
    return df.loc[df[ts].gt(t0 - pd.Timedelta(days=days)) & df[ts].le(end)].copy()


def contract_days(df, t0):
    df = available(df, t0, contract=True)
    df = df.sort_values(['created_ts', 'contract_id']).groupby('service_instance_id').tail(1)
    return np.floor((df.contract_end_date - t0).dt.total_seconds() / 86400).set_axis(df.service_instance_id)


def balances(df):
    df = df.copy()
    df['_invoice'] = df.invoice_id.fillna('').replace('', '__CUSTOMER_BALANCE__')
    df = df.sort_values(['transaction_ts', 'balance_history_id']).groupby(['customer_id', '_invoice']).tail(1)
    return pd.to_numeric(df.outstanding_amount, errors='raise').groupby(df.customer_id).sum(min_count=1)


def validate_units(df):
    data = df.usage_type.str.upper().isin(['DATA', 'ROAMING_DATA'])
    if not df.loc[data, 'usage_unit'].str.upper().eq('MB').all():
        raise ValueError('Non-MB data usage requires an agreed Python/SQL unit conversion contract')


def read_reference(path):
    if sha(path) != REFERENCE_SHA:
        raise ValueError('Reference training ZIP checksum mismatch')
    prefix = 'com01_pit_training_dataset_v0_1/'
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read(prefix + 'generation_manifest.json'))
        if manifest['input_zip_sha256'] != SOURCE_SHA:
            raise ValueError('Reference source lineage mismatch')
        frames = {}
        # Strict allowlist. Do not open or extract the OOT member.
        for role in ['train', 'validation']:
            name = 'COM01_' + role + '.csv'
            content = z.read(prefix + name)
            if hashlib.sha256(content).hexdigest() != manifest['outputs'][name]['sha256']:
                raise ValueError(role + ' reference member checksum mismatch')
            f = pd.read_csv(io.BytesIO(content))
            if f.training_observation_id.isna().any() or not f.training_observation_id.is_unique:
                raise ValueError('Invalid reference observation IDs')
            f['data_as_of_ts'] = pd.to_datetime(f.data_as_of_ts, utc=True, errors='raise')
            f['label_matured_ts'] = pd.to_datetime(f.label_matured_ts, utc=True, errors='raise')
            if not (f.label_matured_ts == f.data_as_of_ts + pd.Timedelta(days=30)).all():
                raise ValueError('Reference label horizon differs from 30 days')
            if not f.churn_30d.isin([0, 1]).all():
                raise ValueError('Non-binary reference label')
            if not f.split_role.eq(role.upper()).all():
                raise ValueError('Reference split role mismatch')
            frames[role] = f
    if set(frames['train'].training_observation_id) & set(frames['validation'].training_observation_id):
        raise ValueError('Reference observation overlap')
    if frames['train'].label_matured_ts.max() > frames['validation'].data_as_of_ts.min():
        raise ValueError('Reference training label maturity overlaps validation')
    return frames, manifest


def replay(tables, reference, t0):
    out = reference.drop(columns=FEATURES).copy()
    out['service_tenure_days'] = reference.available_history_days.to_numpy()

    def put(name, values, key, zero=False):
        out[name] = out[key].map(values)
        if zero:
            out[name] = out[name].fillna(0)

    usage = available(tables['usage_event'], t0)
    curr = window(usage, 'event_ts', t0, 30)
    prev = window(usage, 'event_ts', t0, 60, t0 - pd.Timedelta(days=30))
    for name, part in [('usage_data_mb_sum_30d', curr), ('usage_data_mb_sum_prev30d', prev)]:
        data = part.loc[part.usage_type.str.upper().isin(['DATA', 'ROAMING_DATA'])].copy()
        data['usage_quantity'] = pd.to_numeric(data.usage_quantity, errors='raise')
        put(name, data.groupby('service_instance_id').usage_quantity.sum(), 'service_instance_id', True)
    put('usage_active_days_count_30d', curr.event_ts.dt.floor('D').groupby(curr.service_instance_id).nunique(), 'service_instance_id', True)
    out['usage_data_mb_delta_30d_vs_prev30d'] = out.usage_data_mb_sum_30d - out.usage_data_mb_sum_prev30d
    inv = window(available(tables['invoice'], t0), 'invoice_date', t0, 90)
    inv['invoice_amount'] = pd.to_numeric(inv.invoice_amount, errors='raise')
    put('arpu_sgd', inv.groupby('customer_id').invoice_amount.mean(), 'customer_id')
    balance = window(available(tables['invoice_balance_history'], t0), 'transaction_ts', t0, 90)
    put('billing_overdue_amount_sgd', balances(balance), 'customer_id')
    pay = window(available(tables['payment_transaction'], t0), 'transaction_ts', t0, 90)
    pay = pay.loc[pay.payment_status.str.upper().isin(['FAILED', 'OVERDUE', 'DECLINED', 'REJECTED', 'RETURNED'])]
    put('billing_payment_failure_count_90d', pay.groupby('customer_id').size(), 'customer_id', True)
    for table, ts, name in [('complaint', 'submitted_ts', 'care_complaint_count_30d'),
                            ('customer_interaction', 'started_ts', 'care_repeat_contact_count_30d')]:
        part = window(available(tables[table], t0), ts, t0, 30)
        counts = part.groupby('customer_id').size()
        if table == 'customer_interaction':
            counts = (counts - 1).clip(lower=0)
        put(name, counts, 'customer_id', True)
    impacts = window(available(tables['service_impact_event'], t0), 'detected_ts', t0, 30)
    put('network_incident_count_30d', impacts.groupby('service_instance_id').size(), 'service_instance_id', True)
    ends = impacts.resolved_ts.where(impacts.resolved_ts.notna() & impacts.resolved_ts.le(t0), t0)
    minutes = ((ends - impacts.detected_ts).dt.total_seconds() / 60).clip(lower=0)
    put('network_degraded_minutes_30d', minutes.groupby(impacts.service_instance_id).sum(), 'service_instance_id', True)
    digital = window(available(tables['digital_session'], t0), 'started_ts', t0, 30)
    put('digital_active_days_count_30d', digital.started_ts.dt.floor('D').groupby(digital.customer_id).nunique(), 'customer_id', True)
    orders = window(available(tables['product_order'], t0), 'submitted_ts', t0, 90)
    orders = orders.loc[orders.order_type.str.upper().isin(['PLAN_CHANGE', 'ADD_ON_CHANGE'])]
    put('product_change_count_90d', orders.groupby('service_instance_id').size(), 'service_instance_id', True)
    put('contract_remaining_days', contract_days(tables['contract_detail'], t0), 'service_instance_id')
    if not out.churn_30d.equals(reference.churn_30d):
        raise ValueError('Label preservation failed')
    return out


def build(source, reference_zip, output):
    source, reference_zip, output = Path(source).resolve(), Path(reference_zip).resolve(), Path(output).resolve()
    if sha(source) != SOURCE_SHA:
        raise ValueError('Historical source checksum mismatch')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output folder must be new or empty; existing evidence is not overwritten')
    frames, manifest = read_reference(reference_zip)
    reference = pd.concat(frames.values(), ignore_index=True)
    services, customers = set(reference.service_instance_id), set(reference.customer_id)
    tables = {}
    with zipfile.ZipFile(source) as z:
        names = z.namelist()
        if any(token in name.lower() for token in FORBIDDEN for name in names):
            raise ValueError('Private or truth source archive rejected')
        roots = [n[:-len('historical_t0_schedule.csv')] for n in names if n.endswith('/SOURCE_HISTORY_SAFE/historical_t0_schedule.csv')]
        if len(roots) != 1:
            raise ValueError('Expected exactly one safe historical source root')
        root = roots[0]
        # ID inventory only. No OOT feature or label file is read.
        with z.open(root + 'data/service_instance.csv') as f:
            source_services = set(pd.read_csv(f, usecols=['service_instance_id']).service_instance_id)
        excluded = sorted(source_services - services)
        if not services <= source_services or not excluded:
            raise ValueError('Invalid development service membership')
        for table, cols in TABLES.items():
            cols = list(dict.fromkeys(cols + ['created_ts', 'ingested_ts']))
            with z.open(root + 'data/' + table + '.csv') as f:
                df = pd.read_csv(f, usecols=cols, low_memory=False)
            key = 'service_instance_id' if 'service_instance_id' in df else 'customer_id'
            df = df.loc[df[key].isin(services if key == 'service_instance_id' else customers)].copy()
            for col in df.columns:
                if col.endswith('_ts') or col.endswith('_date'):
                    df[col] = pd.to_datetime(df[col], utc=True, errors='raise')
            tables[table] = df
            print('Loaded development source:', table, len(df), flush=True)
    validate_units(tables['usage_event'])
    parts, changes = [], []
    for t0, group in reference.groupby('data_as_of_ts', sort=True):
        group = group.reset_index(drop=True)
        actual = replay(tables, group, t0)
        changed = {}
        for feature in FEATURES:
            changed[feature] = int((~np.isclose(actual[feature].to_numpy(float), group[feature].to_numpy(float), equal_nan=True, rtol=1e-8, atol=1e-6)).sum())
        changes.append({'as_of': str(t0), 'observations': len(actual), 'changed_cells_by_feature': changed})
        parts.append(actual)
        print('Replayed development date:', t0, len(actual), flush=True)
    result = pd.concat(parts, ignore_index=True)
    report = {'status': 'CANDIDATE_BLOCKED', 'source_sha256': SOURCE_SHA,
              'reference_zip_sha256': REFERENCE_SHA, 'oot_opened': False, 'blind_opened': False,
              'labels': 'Copied from checksum-verified original development CSVs; no independent relabelling approval',
              'population': 'Original development observations retained; serving population parity pending',
              'python_sql_runtime_parity': 'NOT_RUN', 'changes': changes, 'splits': {},
              'excluded_non_development_services': len(excluded),
              'exclusion_scope': 'Conservative source-ID complement of verified development membership; includes reserved and ineligible services, not an exact OOT count',
              'blockers': ['PostgreSQL feature/population parity not run', 'Historical mutable source versions require verification', 'Independent label and source completeness review pending']}
    output.mkdir(parents=True, exist_ok=True)
    cfg = {'purpose': 'historical_development', 'source_path': str(source), 'source_sha256': SOURCE_SHA,
           'feature_corrections_verified': False, 'evidence_reference': str(output / 'rebuild_report.json')}
    for role in ['train', 'validation']:
        original = frames[role].set_index('training_observation_id')
        f = result.set_index('training_observation_id').loc[original.index].reset_index()
        if not f.churn_30d.to_numpy().tolist() == original.churn_30d.to_numpy().tolist():
            raise ValueError('Split labels changed')
        f = f.rename(columns={'churn_30d': 'label'})
        path = output / ('COM01_' + role + '.csv')
        f.to_csv(path, index=False)
        cfg[role] = {'path': str(path), 'sha256': sha(path)}
        missing = {feature: float(f[feature].isna().mean()) for feature in FEATURES}
        failures = [feature for feature, rate in missing.items() if rate > (.6 if feature == 'contract_remaining_days' else .3)]
        report['splits'][role] = {'observations': len(f), 'services': int(f.service_instance_id.nunique()),
                                  'positives': int(f.label.sum()), 'missing_fraction': missing, 'coverage_failures': failures}
        for feature in failures:
            report['blockers'].append(role + ' feature coverage failed: ' + feature)
    path = output / 'excluded_non_development_service_ids.json'
    path.write_text(json.dumps(excluded, indent=2))
    cfg['heldout_service_ids'] = {'path': str(path), 'sha256': sha(path)}
    report['builder_sha256'] = sha(Path(__file__))
    (output / 'rebuild_report.json').write_text(json.dumps(report, indent=2))
    (output / 'dataset.json').write_text(json.dumps(cfg, indent=2))
    print('Candidate written; training remains blocked. Report:', output / 'rebuild_report.json')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    build(args.source, args.reference, args.output)
