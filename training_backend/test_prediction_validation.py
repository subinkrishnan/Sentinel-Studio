import csv,io,json,tempfile,unittest
from pathlib import Path
from prediction_validation import compare


def data(rows, dev=False):
    out=io.StringIO();fields=['training_observation_id','service_instance_id','data_as_of_ts','probability','threshold','predicted_label']+(['model_name','model_version'] if dev else ['label'])
    writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader();writer.writerows(rows);return out.getvalue()


class PredictionValidation(unittest.TestCase):
    def setUp(self):
        self.local=[dict(training_observation_id='o'+str(i),service_instance_id='s'+str(i),data_as_of_ts='2026-07-02T00:00:00+00:00',probability=p,threshold=.5,predicted_label=int(p>=.5),label=i) for i,p in enumerate([.1,.8])]
        self.dev=[{**{k:v for k,v in row.items() if k!='label'},'model_name':'com01_experiment_test','model_version':'v0.5.0'} for row in self.local]
    def run_check(self):return compare(data(self.local),data(self.dev,True),'com01_experiment_test','v0.5.0')
    def test_exact_and_reordered_match(self):
        self.dev.reverse();self.dev[0]['data_as_of_ts']='2026-07-02T08:00:00+08:00'
        report=self.run_check();self.assertEqual(report['status'],'PREDICTION_PARITY_PASS');self.assertEqual(report['dev_metrics_on_matched_rows']['accuracy'],1);self.assertFalse(report['production_publication_allowed']);self.assertFalse(report['live_sdk_fetch_verified'])
    def test_probability_tolerance_and_threshold_crossing(self):
        self.dev[0]['probability']+=5e-8;self.assertEqual(self.run_check()['status'],'PREDICTION_PARITY_PASS')
        self.dev[0]['probability']+=1e-5;self.assertEqual(self.run_check()['checks']['probability_mismatches'],1)
        self.local[0].update(probability=.49999999,predicted_label=0);self.dev[0].update(probability=.50000001,predicted_label=1)
        report=self.run_check();self.assertEqual(report['checks']['probability_mismatches'],0);self.assertEqual(report['checks']['classification_mismatches'],1);self.assertEqual(report['status'],'PREDICTION_PARITY_FAIL')
    def test_missing_extra_and_duplicates_fail(self):
        self.dev.pop();self.assertEqual(self.run_check()['checks']['missing_observations'],1)
        self.dev.append(dict(self.dev[0]));self.assertEqual(self.run_check()['checks']['duplicate_observations'],1)
        self.dev[1].update(training_observation_id='extra',service_instance_id='other');self.assertEqual(self.run_check()['checks']['unexpected_observations'],1)
    def test_wrong_identity_and_threshold_fail(self):
        self.dev[0].update(model_version='v9.0.0',threshold=.2,predicted_label=1)
        report=self.run_check();self.assertEqual(report['checks']['model_identity_mismatches'],1);self.assertEqual(report['checks']['threshold_mismatches'],1);self.assertEqual(report['checks']['inconsistent_dev_decisions'],1)
    def test_malformed_data_blocked(self):
        for value in ['nan','inf',-1,1.1]:
            self.dev[0]['probability']=value
            with self.assertRaises(ValueError):self.run_check()
        self.dev[0]['probability']=.1;self.dev[0]['data_as_of_ts']='2026-07-02'
        with self.assertRaises(ValueError):self.run_check()
        with self.assertRaises(ValueError):compare(data(self.local),data([],True),'m','v')
    def test_admin_records_immutable_attempts(self):
        from admin_server import Admin
        from server import sha
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);results=root/'run/results';results.mkdir(parents=True)
            for name,content in [('XGB_validation_predictions.csv',data(self.local)),('XGB_serving.joblib','test serving bytes'),('XGB_serving_parity.json','{}')]:
                (results/name).write_text(content)
            admin=Admin.__new__(Admin);admin.root=root;admin.lock=__import__('threading').RLock()
            run={'id':'run','status':'COMPLETED','artifacts':[{'name':p.name,'sha256':sha(p)} for p in results.iterdir()], 'staging_identity':{'run':'run','model':'XGB','name':'com01_experiment_test','version':'v0.5.0','serving_sha256':sha(results/'XGB_serving.joblib')}}
            admin.runs={'run':run}
            admin.validate_predictions('run','XGB',data(self.dev,True))
            first=run['prediction_validation']['XGB']['artifact']
            self.dev.pop();admin.validate_predictions('run','XGB',data(self.dev,True))
            self.assertEqual(run['prediction_validation']['XGB']['status'],'PREDICTION_PARITY_FAIL')
            self.assertTrue((results/first).is_file());self.assertEqual(json.loads((results/first).read_text())['status'],'PREDICTION_PARITY_PASS')
            self.assertNotEqual(first,run['prediction_validation']['XGB']['artifact'])
            with self.assertRaises(ValueError):admin.validate_predictions('run','LR',data(self.dev,True))
