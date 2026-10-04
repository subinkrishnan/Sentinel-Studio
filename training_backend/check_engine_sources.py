"""Read-only engine source inventory. Never scores, uploads or promotes a model."""
import argparse
import getpass
import json
import re
from pathlib import Path


def inspect_sources(client, manifest):
    sources = manifest['sources']
    for source in sources:
        if not re.fullmatch(r'tmform_[a-z0-9_]+', source['name']):
            raise ValueError('Unexpected source table name in local manifest')
    columns = client.query("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name LIKE 'bronze%'
        ORDER BY table_name, ordinal_position
    """)
    schema = {}
    for row in columns:
        schema.setdefault(row['table_name'], {})[row['column_name']] = row['data_type']
    report = {
        'local_source_version': manifest.get('version'),
        'operation': 'READ_ONLY_SCHEMA_AND_ROW_COUNTS',
        'source_identity': 'UNVERIFIED: matching counts do not prove identical contents',
        'blind_or_reserved_evaluated': False,
        'model_staged': False,
        'sources': [],
    }
    for source in sources:
        name = 'bronze__' + source['name']
        entry = {'table': name, 'local_rows': source['rows'], 'exists': name in schema}
        entry['missing_columns'] = sorted(set(source['columns']) - set(schema.get(name, {})))
        if entry['exists']:
            try:
                rows = client.query('SELECT COUNT(*) AS row_count FROM public.' + name)
                entry['engine_rows'] = int(rows[0]['row_count'])
                entry['row_count_matches'] = entry['engine_rows'] == entry['local_rows']
            except Exception as exc:
                # Only the error class is retained; SDK messages can contain sensitive context.
                entry['count_error_type'] = type(exc).__name__
        report['sources'].append(entry)
        print(name + ': engine=' + str(entry.get('engine_rows', 'unavailable'))
              + ' local=' + str(entry['local_rows'])
              + ' missing_columns=' + str(len(entry['missing_columns'])), flush=True)
    report['schema_and_counts_match'] = all(
        x['exists'] and not x['missing_columns'] and x.get('row_count_matches', False)
        for x in report['sources']
    )
    report['next_gate'] = ('CONTENT_IDENTITY_AND_FEATURE_PARITY_REQUIRED'
                           if report['schema_and_counts_match']
                           else 'SOURCE_PACKAGE_OR_SCHEMA_ALIGNMENT_REQUIRED')
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
        report = inspect_sources(client, manifest)
    except Exception as exc:
        raise SystemExit('Diagnostic stopped: ' + type(exc).__name__
                         + '. Credentials and raw error details were not saved.') from None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('NEXT GATE: ' + report['next_gate'])
    print('Report: ' + str(args.output))


if __name__ == '__main__':
    main()
