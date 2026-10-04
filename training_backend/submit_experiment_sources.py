"""Verify v0.5 sources and submit isolated Bronze schemas for checker provisioning.

No ingest, refresh, model push, self approval, or production publication occurs.
"""
import argparse
import csv
import gzip
import hashlib
import json
import re
from pathlib import Path

from check_engine_sources import safe_error


def build_plan(data_dir):
    data_dir = Path(data_dir).resolve()
    manifest_path = data_dir / 'source_manifest.json'
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get('version') != '0.5.0-SOURCE-FIRST-BENCHMARK':
        raise ValueError('Expected the frozen v0.5 development source manifest')
    sources = manifest['sources']
    if len(sources) != 13 or len({s['name'] for s in sources}) != 13:
        raise ValueError('Expected 13 distinct development source tables')
    digest = hashlib.sha256(raw).hexdigest()
    # Different source manifests receive different namespaces, preventing mixing.
    prefix = 'com01v05_' + digest[:8] + '_'
    plan = {'manifest_sha256': digest, 'namespace': prefix, 'tables': [],
            'scope': 'LOCAL_V05_DEVELOPMENT_ONLY', 'records_uploaded': False,
            'checker_required': True, 'production_publication_allowed': False}
    for source in sources:
        if not re.fullmatch(r'tmform_[a-z0-9_]+', source['name']):
            raise ValueError('Unexpected source table name')
        if not all(re.fullmatch(r'[a-z][a-z0-9_]*', c) for c in source['columns']):
            raise ValueError('Unexpected source column name')
        path = (data_dir / source['path']).resolve()
        if not path.is_relative_to(data_dir) or path.suffix != '.gz':
            raise ValueError('Source must be a gzip CSV inside the development dataset')
        hasher = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                hasher.update(chunk)
        if hasher.hexdigest() != source['sha256']:
            raise ValueError('Source checksum mismatch: ' + source['name'])
        with gzip.open(path, 'rt', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            if next(reader) != source['columns']:
                raise ValueError('CSV header differs from manifest: ' + source['name'])
        name = prefix + source['name']
        if len('bronze__' + name) > 63:
            raise ValueError('Experimental table name exceeds PostgreSQL identifier limit')
        plan['tables'].append({
            'name': name,
            # The engine owns source_system. Preserve the original payload value
            # separately; later ingestion must apply this explicit mapping.
            'payload_column_map': {'source_system': 'upstream_source_system'}
                                  if 'source_system' in source['columns'] else {},
            'columns': [{'name': ('upstream_source_system' if c == 'source_system' else c),
                         'dtype': 'text'} for c in source['columns']],
            'title': 'COM01 v0.5 experiment: ' + source['name'],
            'description': ('Isolated synthetic development data. Source gzip SHA256 '
                            + source['sha256'] + '; rows ' + str(source['rows'])
                            + '. No original blind data. Not production qualified.'),
            'source_name': source['name'], 'source_path': str(path),
            'source_sha256': source['sha256'], 'expected_rows': source['rows'],
        })
    return plan


def sdk_status(entry):
    response = entry.get('sdk_response')
    if not isinstance(response, list) or len(response) != 1:
        return 'unknown'
    return response[0].get('status', 'unknown')


def submit(client, plan, output, credentials=(), previous=None):
    report = {k: v for k, v in plan.items() if k != 'tables'}
    report['operation'] = 'MAKER_SCHEMA_SUBMISSION_ONLY'
    report['responses'] = []
    old = {}
    if previous is not None:
        if previous.get('manifest_sha256') != plan['manifest_sha256']:
            raise ValueError('Previous submission belongs to another source manifest')
        old = {entry['name']: entry for entry in previous['responses']}
        if set(old) != {table['name'] for table in plan['tables']}:
            raise ValueError('Previous submission has a different table inventory')
    for table in plan['tables']:
        if table['name'] in old:
            earlier = old[table['name']]
            status = sdk_status(earlier)
            if status in ('submitted', 'provisioned'):
                report['responses'].append(earlier)
                output.write_text(json.dumps(report, indent=2, default=str) + '\n')
                print(table['name'] + ': retained ' + status + '; no API write', flush=True)
                continue
            if status != 'error' and 'error' not in earlier:
                raise ValueError('Cannot safely retry unknown SDK status for ' + table['name'])
        spec = {k: table[k] for k in ('name', 'columns', 'title', 'description')}
        try:
            # No checker and no records: SDK creates/submits schemas only.
            response = client.onboard_bronze([spec])
            serialized = json.dumps(response, default=str)
            for credential in credentials:
                if credential:
                    serialized = serialized.replace(credential, '[REDACTED]')
            response = json.loads(serialized)
            entry = {'name': table['name'], 'sdk_response': response}
            print(table['name'] + ': ' + sdk_status(entry), flush=True)
        except Exception as exc:
            entry = {'name': table['name'], 'error': safe_error(exc, credentials)}
            report['responses'].append(entry)
            output.write_text(json.dumps(report, indent=2, default=str) + '\n')
            raise RuntimeError('Submission stopped; partial responses saved. '
                               + entry['error']) from None
        report['responses'].append(entry)
        output.write_text(json.dumps(report, indent=2, default=str) + '\n')
    errors = sum(sdk_status(entry) not in ('submitted', 'provisioned')
                 for entry in report['responses'])
    print('Schema submission requests finished. Unresolved responses: ' + str(errors))
    print('A different checker identity must provision tables before ingestion.')
    if errors:
        raise RuntimeError('Some schemas were not submitted; inspect the saved SDK responses')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--submit', action='store_true', help='Submit experimental schemas as maker')
    p.add_argument('--retry-failed', action='store_true',
                   help='Keep submitted IDs and retry only failures in the previous report')
    args = p.parse_args()
    plan = build_plan(args.data_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    previous = None
    if args.retry_failed:
        if not args.submit:
            raise SystemExit('--retry-failed requires --submit')
        status_path = args.output_dir / 'source-onboarding-status.json'
        previous = json.loads(status_path.read_text())
        backup = args.output_dir / 'source-onboarding-status.before-retry.json'
        if not backup.exists():
            backup.write_text(json.dumps(previous, indent=2) + '\n')
    (args.output_dir / 'source-onboarding-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    print('13 source checksums and CSV headers: PASS')
    print('Experimental namespace: ' + plan['namespace'])
    if not args.submit:
        print('Plan prepared. No engine calls made.')
        return
    import getpass
    from sentinel_client import Client
    cid = getpass.getpass('Client ID: ').strip().removeprefix('client_id=').strip()
    secret = getpass.getpass('Client Secret: ').strip().removeprefix('client_secret=').strip()
    if not cid or not secret:
        raise SystemExit('Both credentials are required')
    client = Client('https://dev.sentinel.inalpha.ai', cid, secret)
    try:
        if client.query('SELECT 1 AS ok') != [{'ok': 1}]:
            raise ValueError('Unexpected connection response')
        submit(client, plan, args.output_dir / 'source-onboarding-status.json',
               (cid, secret), previous)
    except Exception as exc:
        raise SystemExit(safe_error(exc, (cid, secret))) from None
    print('Report: ' + str(args.output_dir / 'source-onboarding-status.json'))


if __name__ == '__main__':
    main()
