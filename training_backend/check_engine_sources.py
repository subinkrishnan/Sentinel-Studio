"""Read-only engine source inventory. Never scores, uploads or promotes a model."""
import argparse
import getpass
import json
import re
from pathlib import Path


def safe_error(exc, credentials=()):
    message = str(exc)
    for value in credentials:
        if value:
            message = message.replace(value, '[REDACTED]')
    message = re.sub(r'[A-Za-z0-9_+/=.-]{24,}', '[REDACTED]', message)
    return type(exc).__name__ + ': ' + message[:800]


def inspect_sources(client, manifest, credentials=()):
    sources = manifest['sources']
    for source in sources:
        if not re.fullmatch(r'tmform_[a-z0-9_]+', source['name']):
            raise ValueError('Unexpected source table name in local manifest')
    metadata_error = None
    try:
        columns = client.query("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name LIKE 'bronze%'
        ORDER BY table_name, ordinal_position
        """)
    except Exception as exc:
        columns = []
        metadata_error = safe_error(exc, credentials)
    schema = {}
    for row in columns:
        schema.setdefault(row['table_name'], {})[row['column_name']] = row['data_type']
    report = {
        'local_source_version': manifest.get('version'),
        'operation': 'READ_ONLY_SCHEMA_AND_ROW_COUNTS',
        'source_identity': 'UNVERIFIED: matching counts do not prove identical contents',
        'blind_or_reserved_evaluated': False,
        'model_staged': False,
        'metadata_rows_returned': len(columns),
        'metadata_error': metadata_error,
        'sources': [],
    }
    for source in sources:
        name = 'bronze__' + source['name']
        entry = {'table': name, 'local_rows': source['rows'],
                 'exists': True if name in schema else None,
                 'metadata_visible': name in schema}
        entry['missing_columns'] = (sorted(set(source['columns']) - set(schema[name]))
                                    if name in schema else None)
        # information_schema can hide tables visible through an approved gateway.
        # Test access directly even when metadata is absent; never infer absence.
        try:
            rows = client.query('SELECT COUNT(*) AS row_count FROM public.' + name)
            entry['engine_rows'] = int(rows[0]['row_count'])
            entry['exists'] = True
            entry['row_count_matches'] = entry['engine_rows'] == entry['local_rows']
            entry['direct_read_status'] = 'PASS'
        except Exception as exc:
            entry['direct_read_status'] = 'FAILED_OR_DENIED'
            entry['count_error'] = safe_error(exc, credentials)
        report['sources'].append(entry)
        print(name + ': engine=' + str(entry.get('engine_rows', 'unavailable'))
              + ' local=' + str(entry['local_rows'])
              + ' schema=' + ('visible' if entry['metadata_visible'] else 'unavailable')
              + ' access=' + entry['direct_read_status'], flush=True)
        if entry.get('count_error'):
            print('  ' + entry['count_error'], flush=True)
    report['schema_and_counts_match'] = all(
        x['metadata_visible'] and not x['missing_columns'] and x.get('row_count_matches', False)
        for x in report['sources']
    )
    if any(x['direct_read_status'] != 'PASS' for x in report['sources']):
        report['next_gate'] = 'SOURCE_ACCESS_OR_TABLE_RESOLUTION_REQUIRED'
    elif any(not x['row_count_matches'] for x in report['sources']):
        report['next_gate'] = 'SOURCE_POPULATION_DIFFERENCE_REQUIRES_RECONCILIATION'
    elif not report['schema_and_counts_match']:
        report['next_gate'] = 'SOURCE_SCHEMA_VERIFICATION_REQUIRED'
    else:
        report['next_gate'] = 'CONTENT_IDENTITY_AND_FEATURE_PARITY_REQUIRED'
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    manifest = json.loads((args.data_dir / 'source_manifest.json').read_text())
    cid = getpass.getpass('Client ID: ').strip().removeprefix('client_id=').strip()
    secret = getpass.getpass('Client Secret: ').strip().removeprefix('client_secret=').strip()
    if not cid or not secret:
        raise SystemExit('Both credentials are required.')
    from sentinel_client import Client
    client = Client('https://dev.sentinel.inalpha.ai', cid, secret)
    try:
        if client.query('SELECT 1 AS ok') != [{'ok': 1}]:
            raise ValueError('Unexpected connection response')
        print('Connection: PASS. Checking 13 source tables; no scoring or writes.', flush=True)
        report = inspect_sources(client, manifest, (cid, secret))
    except Exception as exc:
        raise SystemExit('Diagnostic stopped: ' + type(exc).__name__
                         + '. Credentials and raw error details were not saved.') from None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('NEXT GATE: ' + report['next_gate'])
    print('Report: ' + str(args.output))


if __name__ == '__main__':
    main()
