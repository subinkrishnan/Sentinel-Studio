"""HTTP integration checks: shared Studio session and private API routing."""
import http.client,json,threading,unittest
from unittest.mock import Mock,patch
from admin_server import make_http_server

class StudioIntegration(unittest.TestCase):
 def setUp(self):
  self.admin=Mock();self.admin.status.return_value={'dataset':None,'runs':[],'engine':{'status':'NOT_CONNECTED'}}
  self.admin.start.return_value={'id':'test-run'}
  self.server=make_http_server(self.admin,0,'test-access-token-for-local-checks')
  self.port=self.server.server_address[1];self.origin=f'http://127.0.0.1:{self.port}'
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.cookie=''
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join()
 def request(self,path,method='GET',body=None,origin=None):
  c=http.client.HTTPConnection('127.0.0.1',self.port);headers={'Origin':origin or self.origin,'Cookie':self.cookie,'Content-Type':'application/json'}
  c.request(method,path,json.dumps(body) if body is not None else None,headers)
  r=c.getresponse();status=r.status;data=r.read();cookie=r.getheader('Set-Cookie');c.close();return status,data,cookie
 def login(self):
  status,_,cookie=self.request('/api/session','POST',{'token':'test-access-token-for-local-checks'});self.assertEqual(status,200);self.assertIn('HttpOnly',cookie);self.cookie=cookie.split(';')[0]
 def test_shared_session_navigation_and_logout(self):
  self.assertIn(b'id="token"',self.request('/training.html')[1]);self.assertEqual(self.request('/api/status')[0],401)
  self.login()
  self.assertIn(b'data-runner-session="true"',self.request('/')[1])
  self.assertIn(b'href="training.html"',self.request('/index.html')[1])
  console=self.request('/training.html')[1];self.assertIn(b'data-tab="runs"',console);self.assertIn(b'href="index.html#brief"',console)
  self.assertEqual(self.request('/api/status')[0],200)
  self.request('/api/logout','POST',{});self.assertEqual(self.request('/api/status')[0],401)
  self.assertIn(b'id="token"',self.request('/index.html')[1])
 def test_static_allowlist_and_bad_origin(self):
  for asset in ['/app.js','/brief.js','/styles.css','/demo-login.js','/training.js','/mart.js']:
   self.assertEqual(self.request(asset)[0],200,asset)
  self.assertEqual(self.request('/api/session','POST',{'token':'test-access-token-for-local-checks'},origin='https://other.example')[0],403)
  self.login()
  for path in ['/training_backend/admin.example.json','/training_backend/admin_server.py','/../PRIVATE_TRAINING.md']:
   self.assertEqual(self.request(path)[0],404,path)
 def test_training_and_staging_use_existing_admin(self):
  self.login();self.assertEqual(self.request('/api/runs','POST',{})[0],202);self.admin.start.assert_called_once()
  self.admin.stage.return_value={'status':'STAGING_PUSH_SUBMITTED'}
  self.assertEqual(self.request('/api/engine/stage','POST',{'run':'test-run','model':'XGB'})[0],200);self.admin.stage.assert_called_once_with('test-run','XGB')
  with patch('admin_server.engine.connect',return_value={'status':'CONNECTED'}):self.assertEqual(self.request('/api/engine/connect','POST',{})[0],200)
 def test_mart_api_is_private_and_configured(self):
  self.assertEqual(self.request('/api/mart/summary')[0],401)
  self.login();self.admin.config={'mart':{'enabled':False}}
  with patch('admin_server.mart.snapshot',return_value={'status':'NOT_CONFIGURED','data':None}) as summary:
   status,body,_=self.request('/api/mart/summary')
  self.assertEqual(status,200);self.assertEqual(json.loads(body)['status'],'NOT_CONFIGURED')
  summary.assert_called_once_with({'enabled':False})
 def test_prediction_validation_requires_session_and_routes_selected_run(self):
  body={'run':'test-run','model':'XGB','csv':'export'}
  self.assertEqual(self.request('/api/predictions/validate','POST',body)[0],401)
  self.admin.validate_predictions.assert_not_called()
  self.login();self.admin.validate_predictions.return_value={'status':'PREDICTION_PARITY_FAIL'}
  status,response,_=self.request('/api/predictions/validate','POST',body)
  self.assertEqual(status,200);self.assertEqual(json.loads(response)['status'],'PREDICTION_PARITY_FAIL')
  self.admin.validate_predictions.assert_called_once_with('test-run','XGB','export')
 def test_missing_credentials_reported_from_service_environment(self):
  self.login()
  with patch.dict('os.environ',{},clear=True):
   status,body,_=self.request('/api/engine/connect','POST',{})
  self.assertEqual(status,409);data=json.loads(body)
  self.assertEqual(data['connection']['code'],'MISSING_CREDENTIALS')
  self.assertIn('SENTINEL_CLIENT_ID',data['error']);self.assertIn('SENTINEL_CLIENT_SECRET',data['error'])
  self.assertEqual(self.admin.connection['status'],'BLOCKED')
 def test_sdk_exception_is_redacted(self):
  self.login()
  with patch('admin_server.engine.connect',side_effect=RuntimeError('sensitive-sdk-credential')):
   status,body,_=self.request('/api/engine/connect','POST',{})
  self.assertEqual(status,409);self.assertNotIn(b'sensitive-sdk-credential',body)
  self.assertEqual(json.loads(body)['connection']['code'],'DEV_QUERY_FAILED')
if __name__=='__main__':unittest.main()
