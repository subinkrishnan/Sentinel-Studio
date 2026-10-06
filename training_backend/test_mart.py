import json,unittest
from unittest.mock import Mock,patch
from mart import query_for,snapshot,make_client


def settings():
    return {'enabled':True,'mode':'dev_experiment','table':'public.mart__com01v05_0fb5f846_churn','business_line':'Postpaid',
        'columns':{'service_id':'service_instance_id','run_id':'scoring_run_id','as_of':'data_as_of_ts','probability':'churn_probability','risk_band':'risk_band','quality_gate':'quality_gate_status','publication_status':'run_status','model_version':'model_version'}}


def payload():
    return {'run':{'run_id':'published','as_of':'2026-07-02T00:00:00Z','scored':4,'unique_services':4,'high_risk':1,'medium_risk':1,'low_risk':2,'mean_probability':.2,'model_version':'v0.5.0','published':True,'valid':True},'latest_attempt':{'run_id':'rejected'},'trend':[],'segments':[],'reasons':[]}


class MartConnection(unittest.TestCase):
    def test_disabled_never_contacts_engine(self):
        factory=Mock();self.assertEqual(snapshot({},factory)['status'],'NOT_CONFIGURED');factory.assert_not_called()
    def test_read_only_mapping_and_config_switch(self):
        config=settings();sql=query_for(config)
        self.assertIn('public"."mart__com01v05_0fb5f846_churn',sql)
        self.assertIn('COUNT(*)=COUNT(DISTINCT service_id)',sql)
        self.assertIn("BOOL_AND(COALESCE(UPPER(quality_gate)='PASS'",sql)
        config.update(mode='canonical',table='public.mart__churn_prediction_master')
        self.assertIn('mart__churn_prediction_master',query_for(config))
    def test_unsafe_identifiers_and_wrong_layers_rejected(self):
        for relation in ['public.bronze__com01v05_0fb5f846_x','public.mart__x; DROP TABLE x','other.mart__x','public.mart__canonical']:
            config=settings();config['table']=relation
            with self.assertRaises(ValueError):query_for(config)
        config=settings();config['columns']['probability']='p; DROP TABLE x'
        with self.assertRaises(ValueError):query_for(config)
        config=settings();config['mode']='canonical'
        with self.assertRaises(ValueError):query_for(config)
    def test_last_valid_published_run_reported(self):
        sdk=Mock();sdk.query.return_value=[{'snapshot':json.dumps(payload())}]
        result=snapshot(settings(),lambda _:sdk)
        self.assertEqual(result['status'],'CONNECTED');self.assertTrue(result['fallback']);self.assertTrue(result['synthetic']);self.assertTrue(result['pulse_requires_separate_verification'])
    def test_empty_invalid_and_errors_are_not_demo_results(self):
        sdk=Mock();p=payload();p['run']=None;sdk.query.return_value=[{'snapshot':p}]
        self.assertEqual(snapshot(settings(),lambda _:sdk)['status'],'NO_PUBLISHED_DATA')
        p=payload();p['run']['unique_services']=3;sdk.query.return_value=[{'snapshot':p}]
        self.assertEqual(snapshot(settings(),lambda _:sdk)['status'],'BLOCKED')
        sdk.query.side_effect=RuntimeError('secret-token-in-sdk-url')
        result=snapshot(settings(),lambda _:sdk)
        self.assertNotIn('secret-token',json.dumps(result));self.assertIsNone(result['data'])
    def test_production_requires_explicit_host_and_separate_credentials(self):
        config=settings();config.update(mode='canonical',base_url='https://production.example.test',allowed_hosts=['production.example.test'])
        with patch.dict('os.environ',{'SENTINEL_CLIENT_ID':'dev-id','SENTINEL_CLIENT_SECRET':'dev-secret'},clear=True):
            with self.assertRaisesRegex(ValueError,'credentials'):make_client(config)
        config.update(mode='dev_experiment')
        with self.assertRaisesRegex(ValueError,'restricted'):make_client(config)
