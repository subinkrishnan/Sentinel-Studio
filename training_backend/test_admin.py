import unittest,tempfile,os
from unittest.mock import patch
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.linear_model import LogisticRegression
from engine import portable_model,connect,push
class AdminChecks(unittest.TestCase):
 def test_empty_exception_is_visible_and_persisted(self):
  from admin_server import Admin
  with tempfile.TemporaryDirectory() as tmp:
   admin=Admin.__new__(Admin);admin.root=Path(tmp);admin.data=Path(tmp);run={'id':'failure','status':'RUNNING','log':[]}
   with patch('admin_server.verified_training.run',side_effect=AssertionError()):admin.train(run)
   self.assertEqual(run['status'],'FAILED');self.assertIn('AssertionError',run['stage']);self.assertIn('AssertionError',run['log'][0]);self.assertTrue((Path(tmp)/'failure/run.json').exists())
 def test_portable_calibrated_probability(self):
  from scipy.special import logit
  x=pd.DataFrame({'a':np.arange(20)});y=np.array([0,1]*10);base=LogisticRegression().fit(x,y);raw=base.predict_proba(x)[:,1];cal=LogisticRegression().fit(logit(raw).reshape(-1,1),y)
  a={'model':base,'calibrator':cal};np.testing.assert_allclose(portable_model(a).predict_proba(x)[:,1],cal.predict_proba(logit(raw).reshape(-1,1))[:,1],atol=1e-7)
 def test_missing_engine_credentials_blocks(self):
  with patch.dict(os.environ,{},clear=True),self.assertRaisesRegex(ValueError,'credentials'):connect()
 def test_production_origin_rejected(self):
  with patch.dict(os.environ,{'SENTINEL_BASE_URL':'https://sentinel.inalpha.ai'},clear=True),self.assertRaisesRegex(ValueError,'Dev'):connect()
 def test_existing_model_not_overwritten(self):
  with self.assertRaisesRegex(ValueError,'separate'):push(Path('x'),'newchurn10','v1.0.0','SELECT * FROM silver__x',{})
 def test_unreviewed_sql_blocks(self):
  with self.assertRaisesRegex(ValueError,'Silver'):push(Path('x'),'com01_experiment_test','v0.5.0','',{})
 def test_pasted_credential_prefixes_normalised(self):
  import sys,types
  from engine import client
  from unittest.mock import Mock
  sdk=types.ModuleType('sentinel_client');sdk.Client=Mock()
  with patch.dict(os.environ,{'SENTINEL_BASE_URL':'https://dev.sentinel.inalpha.ai','SENTINEL_CLIENT_ID':'  client_id=test-id  ','SENTINEL_CLIENT_SECRET':'  client_secret=test-secret  '},clear=True),patch.dict(sys.modules,{'sentinel_client':sdk}):
   client()
  sdk.Client.assert_called_once_with('https://dev.sentinel.inalpha.ai','test-id','test-secret')
if __name__=='__main__':unittest.main()

