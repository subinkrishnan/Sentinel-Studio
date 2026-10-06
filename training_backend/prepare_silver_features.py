"""Prepare read-only Dev SQL from the frozen COM01 v0.5 feature contract.

No SDK calls, uploads, DDL execution, coverage attestation or config changes.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

FROZEN_SQL_SHA256 = 'e577ccaebc8c58dfad44d3c78a328690009c7ac0339c0a24af685d30a81a486b'
EXPECTED_MANIFEST_PREFIX = '0fb5f846'


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def cutoff_literal(value):
    instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if instant.tzinfo is None:
        raise ValueError('Cutoff must include a timezone')
    return sql_literal(instant.astimezone(timezone.utc).isoformat())


def prepare(manifest_bytes, original_sql, as_of=None):
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    if digest[:8] != EXPECTED_MANIFEST_PREFIX:
        raise ValueError('Use the same frozen source manifest as the current Dev upload')
    manifest = json.loads(manifest_bytes)
    if manifest['version'] != '0.5.0-SOURCE-FIRST-BENCHMARK':
        raise ValueError('Expected source-first benchmark v0.5')
    if hashlib.sha256(original_sql.encode()).hexdigest() != FROZEN_SQL_SHA256:
        raise ValueError('Frozen feature SQL changed')
    sources = manifest['sources']
    names = [s['name'] for s in sources]
    if len(names) != 13 or len(set(names)) != 13:
        raise ValueError('Expected 13 unique source tables')
    if any(not re.fullmatch(r'tmform_[a-z0-9_]+', n) for n in names):
        raise ValueError('Invalid source identifier')
    prefix = 'com01v05_' + digest[:8] + '_'
    coverage_name = 'silver__' + prefix + 'source_coverage'
    mapping = {n: 'public.bronze__' + prefix + n for n in names}
    # Only replace relation tokens following FROM/JOIN. Required-source values
    # remain canonical logical names so coverage is auditable across environments.
    sql = original_sql
    for name, relation in mapping.items():
        sql, count = re.subn(r'\b(FROM|JOIN)\s+' + re.escape(name) + r'\b',
                             lambda m: m[1] + ' ' + relation, sql)
        if count == 0:
            raise ValueError('Source is unused in frozen SQL: ' + name)
    sql = sql.replace('LEFT JOIN com01_source_coverage c',
                      'LEFT JOIN public.' + coverage_name + ' c')
    sql = sql.replace('HAVING COUNT(c.source_table) = 13',
                      'HAVING COUNT(c.source_table) = 13\n       AND COUNT(DISTINCT c.source_table) = 13')
    if as_of is not None:
        sql = sql.replace(':as_of', cutoff_literal(as_of))
    header = ('-- DEV EXPERIMENT ONLY. Read-only feature projection from isolated Bronze sources.\n'
              '-- Coverage control must be independently verified and provisioned first.\n'
              '-- Do not use NOW(): historical benchmark predictions need matching cutoffs.\n')
    queries = []
    for source in sources:
        name = source['name']; relation = mapping[name]
        # Source ingest timestamp is required for historical availability parity.
        queries.append('SELECT ' + sql_literal(name) + ' AS source_name, COUNT(*) AS actual_rows, '
                       + str(int(source['rows'])) + ' AS expected_rows, '
                       + 'MIN(NULLIF(ingested_ts,\'\')::timestamptz) AS earliest_source_ingested_ts, '
                       + 'MAX(NULLIF(ingested_ts,\'\')::timestamptz) AS latest_source_ingested_ts FROM '
                       + relation)
    counts_sql = '-- Read-only. Counts alone do not attest content or historical completeness.\n' + '\nUNION ALL\n'.join(queries) + ';\n'
    contract = {
        'status': 'PREPARED_NOT_DEPLOYED', 'namespace': prefix,
        'source_manifest_sha256': digest, 'frozen_sql_sha256': FROZEN_SQL_SHA256,
        'dev_sql_sha256': hashlib.sha256((header + sql).encode()).hexdigest(),
        'feature_contract': 'COM01_LOCAL_SYNTHETIC_15F_V05',
        'source_mapping': mapping, 'coverage_relation': 'public.' + coverage_name,
        'coverage_columns': {'source_table': 'text', 'population_scope': 'text',
                             'history_start': 'timestamptz', 'complete_through': 'timestamptz'},
        'coverage_key': ['source_table', 'population_scope'],
        'coverage_scope': 'COM01', 'coverage_source_names': names,
        'coverage_fixture_is_attestation': False, 'as_of': as_of,
        'live_content_parity': 'PENDING', 'live_feature_parity': 'PENDING',
        'production_publication_allowed': False,
    }
    return {'features.sql': header + sql, 'source_checks.sql': counts_sql,
            'contract.json': json.dumps(contract, indent=2) + '\n'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--as-of', help='Timezone-qualified benchmark cutoff; omit for :as_of template')
    args = parser.parse_args()
    original = (Path(__file__).parent / 'sql/com01_v05_frozen_features.sql').read_text()
    files = prepare((args.data_dir.expanduser() / 'source_manifest.json').read_bytes(), original, args.as_of)
    output = args.output_dir.expanduser()
    # Never overwrite an earlier reviewed SQL/config/evidence set.
    output.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        (output / name).write_text(content)
    print('Dev feature SQL prepared. No engine changes. Coverage and live parity remain pending.')
    print('Output: ' + str(output.resolve()))


if __name__ == '__main__':
    main()
