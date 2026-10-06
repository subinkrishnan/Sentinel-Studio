"""Read-only, configured Mart summaries. No writes or automatic publication."""
import json
import math
import os
import re
from urllib.parse import urlsplit

REQUIRED = ['service_id', 'run_id', 'as_of', 'probability', 'risk_band', 'quality_gate', 'publication_status', 'model_version']
OPTIONAL = ['segment', 'primary_reason']


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', value):
        raise ValueError('Use explicit SQL identifiers in the Mart mapping')
    return '"' + value + '"'


def query_for(settings):
    mode = settings.get('mode')
    if mode not in ['dev_experiment', 'canonical']:
        raise ValueError('Choose dev_experiment or canonical Mart mode')
    table = settings.get('table', '')
    parts = table.split('.')
    if len(parts) != 2 or parts[0] != 'public' or not parts[1].startswith('mart__'):
        raise ValueError('Configure one public.mart__ relation; Bronze is not a Studio result source')
    relation = '.'.join(identifier(p) for p in parts)
    if mode == 'dev_experiment' and 'com01v05_0fb5f846_' not in parts[1]:
        raise ValueError('Dev experiment Mart must use the isolated COM01 v0.5 namespace')
    if mode == 'canonical' and 'com01v05_' in parts[1]:
        raise ValueError('Canonical mode cannot use an experimental Mart')
    columns = settings.get('columns', {})
    if any(not columns.get(k) for k in REQUIRED):
        raise ValueError('Complete the required Mart column mapping')
    selections = []
    for alias in REQUIRED + OPTIONAL:
        col = columns.get(alias)
        expr = 'NULL::text' if not col else identifier(col) + '::text'
        selections.append(expr + ' AS ' + alias)
    # Payload columns may be text. Empty mandatory values fail the run gate.
    return '''WITH raw AS (
 SELECT ''' + ', '.join(selections) + ''' FROM ''' + relation + '''
), typed AS (
 SELECT *, NULLIF(as_of,'')::timestamptz AS cutoff,
 NULLIF(probability,'')::double precision AS probability_value
 FROM raw
), runs AS (
 SELECT run_id, MAX(cutoff) AS as_of,
 COUNT(*) AS scored, COUNT(DISTINCT service_id) AS unique_services,
 COUNT(*) FILTER (WHERE UPPER(risk_band)='HIGH') AS high_risk,
 COUNT(*) FILTER (WHERE UPPER(risk_band)='MEDIUM') AS medium_risk,
 COUNT(*) FILTER (WHERE UPPER(risk_band)='LOW') AS low_risk,
 AVG(probability_value) AS mean_probability,
 MIN(model_version) AS model_version,
 BOOL_AND(COALESCE(UPPER(quality_gate)='PASS' AND UPPER(publication_status)='PUBLISHED',false)) AS published,
 BOOL_AND(COALESCE(NULLIF(service_id,'') IS NOT NULL AND NULLIF(run_id,'') IS NOT NULL
 AND cutoff IS NOT NULL AND NULLIF(model_version,'') IS NOT NULL
 AND probability_value>=0 AND probability_value<=1
 AND UPPER(risk_band) IN ('HIGH','MEDIUM','LOW'),false))
 AND COUNT(DISTINCT cutoff)=1 AND COUNT(DISTINCT model_version)=1
 AND COUNT(*)=COUNT(DISTINCT service_id) AS valid
 FROM typed GROUP BY run_id
), selected AS (
 SELECT * FROM runs WHERE published AND valid ORDER BY as_of DESC,run_id DESC LIMIT 1
), latest_attempt AS (
 SELECT * FROM runs ORDER BY as_of DESC NULLS LAST,run_id DESC LIMIT 1
), trend AS (
 SELECT * FROM runs WHERE published AND valid ORDER BY as_of DESC,run_id DESC LIMIT 12
), segments AS (
 SELECT COALESCE(NULLIF(t.segment,''),'Unspecified') AS name, COUNT(*) AS scored,
 COUNT(*) FILTER(WHERE UPPER(t.risk_band)='HIGH') AS high_risk
 FROM typed t JOIN selected s ON t.run_id=s.run_id GROUP BY 1
), reasons AS (
 SELECT COALESCE(NULLIF(t.primary_reason,''),'Unavailable') AS name, COUNT(*) AS subscribers
 FROM typed t JOIN selected s ON t.run_id=s.run_id WHERE UPPER(t.risk_band)='HIGH' GROUP BY 1
)
SELECT json_build_object(
 'run',(SELECT row_to_json(s) FROM selected s),
 'latest_attempt',(SELECT json_build_object('run_id',run_id,'as_of',as_of,'published',published,'valid',valid) FROM latest_attempt),
 'trend',COALESCE((SELECT json_agg(json_build_object('run_id',run_id,'as_of',as_of,'scored',scored,'high_risk',high_risk) ORDER BY as_of,run_id) FROM trend),'[]'::json),
 'segments',COALESCE((SELECT json_agg(row_to_json(s) ORDER BY high_risk DESC,name) FROM segments s),'[]'::json),
 'reasons',COALESCE((SELECT json_agg(row_to_json(r) ORDER BY subscribers DESC,name) FROM reasons r),'[]'::json)
) AS snapshot'''


def make_client(settings):
    base = settings.get('base_url', 'https://dev.sentinel.inalpha.ai')
    url = urlsplit(base)
    allowed = settings.get('allowed_hosts', ['dev.sentinel.inalpha.ai'])
    if (url.scheme != 'https' or url.hostname not in allowed or url.username or url.password
            or url.query or url.fragment or url.path not in ['', '/'] or url.port not in [None, 443]):
        raise ValueError('Configure an approved HTTPS Mart endpoint')
    if settings['mode'] == 'dev_experiment' and url.hostname != 'dev.sentinel.inalpha.ai':
        raise ValueError('Experimental Mart reads are restricted to Dev')
    cid = os.environ.get('SENTINEL_MART_CLIENT_ID', '')
    secret = os.environ.get('SENTINEL_MART_CLIENT_SECRET', '')
    if not cid and not secret and url.hostname == 'dev.sentinel.inalpha.ai':
        cid = os.environ.get('SENTINEL_CLIENT_ID', '')
        secret = os.environ.get('SENTINEL_CLIENT_SECRET', '')
    cid = cid.strip().removeprefix('client_id=').strip()
    secret = secret.strip().removeprefix('client_secret=').strip()
    if not cid or not secret:
        raise ValueError('Mart credentials are missing from the service environment')
    from sentinel_client import Client
    return Client(base, cid, secret)


def snapshot(settings, client_factory=make_client):
    if not settings.get('enabled', False):
        return {'status': 'NOT_CONFIGURED', 'reason': 'Mart connection is not configured yet. Bronze ingestion can continue.', 'data': None}
    try:
        sql = query_for(settings)
        result = client_factory(settings).query(sql)
        if not isinstance(result, list) or len(result) != 1 or 'snapshot' not in result[0]:
            raise ValueError('Unexpected Mart response')
        data = result[0]['snapshot']
        if isinstance(data, str):data = json.loads(data)
        if not isinstance(data, dict) or not all(k in data for k in ['run', 'latest_attempt', 'trend', 'segments', 'reasons']):
            raise ValueError('Unexpected Mart summary')
        run = data['run']
        if not run:
            return {'status': 'NO_PUBLISHED_DATA', 'reason': 'No complete, valid PASS/PUBLISHED scoring run is available.', 'data': None}
        if (not run.get('valid') or not run.get('published') or not isinstance(run.get('scored'), int)
                or run['scored'] <= 0 or run.get('unique_services') != run['scored']
                or sum(run.get(k, -1) for k in ['high_risk','medium_risk','low_risk']) != run['scored']):
            raise ValueError('Invalid Mart summary')
        if (not isinstance(run.get('mean_probability'), (int,float))
                or not math.isfinite(run['mean_probability']) or not 0 <= run['mean_probability'] <= 1
                or not all(isinstance(data[k],list) for k in ['trend','segments','reasons'])):
            raise ValueError('Invalid Mart aggregates')
        latest = data['latest_attempt']
        return {'status': 'CONNECTED', 'mode': settings['mode'],
                'business_line': settings.get('business_line', 'Postpaid'),
                'synthetic': settings['mode'] == 'dev_experiment',
                'fallback': bool(latest and latest['run_id'] != run['run_id']),
                'data': data, 'feature_parity': 'SEPARATE_GATE', 'pulse_requires_separate_verification': True}
    except Exception:
        # SDK messages can include URLs or credentials. Never send them to UI.
        return {'status': 'BLOCKED', 'reason': 'Mart read failed. Check the configured endpoint, credentials, table schema and column mapping.', 'data': None}
