"""Authenticated, loopback-only postpaid admin service; no automatic publication."""
import argparse,json,os,secrets,threading,time,uuid,traceback
from pathlib import Path
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from datetime import datetime,timezone
from server import sha
import verified_training,engine

class Admin:
 def __init__(self,config,root):
  self.config=json.loads(Path(config).read_text());self.data=Path(self.config['data_dir']).expanduser().resolve();self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.connection={'status':'NOT_CONNECTED'};self.runs={}
  for p in self.root.glob('*/run.json'):
   r=json.loads(p.read_text())
   if r['status']=='RUNNING':r.update(status='FAILED',stage='Interrupted; preserved for audit');self.save(r)
   self.runs[r['id']]=r
 def save(self,r):
  d=self.root/r['id'];d.mkdir(exist_ok=True);p=d/'run.tmp';p.write_text(json.dumps(r,indent=2));p.replace(d/'run.json')
 def status(self):
  try:
   cfg,frames,_,fit,cal=verified_training.preflight(self.data);dataset={k:{'observations':len(v),'services':int(v.service_instance_id.nunique()),'positives':int(v.label.sum())} for k,v in frames.items()};dataset.update(feature_contract=cfg['feature_contract'],gates='SOURCE_AND_LOCAL_SQL_PASS',fit_observations=len(fit),calibration_observations=len(cal));error=None
  except Exception as e:dataset=None;error=str(e)
  final=None;entry=self.config.get('final_evaluation')
  if entry:
   p=Path(entry['path']).expanduser()
   if sha(p)!=entry['sha256']:error='Final evidence checksum mismatch'
   else:final=json.loads(p.read_text())
  return {'dataset':dataset,'dataset_error':error,'runs':list(self.runs.values())[::-1],'final_evaluation':final,'engine':self.connection,'production_publication_allowed':False}
 def start(self):
  with self.lock:
   if any(r['status']=='RUNNING' for r in self.runs.values()):raise ValueError('A run is already active')
   verified_training.preflight(self.data)
   rid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8];r={'id':rid,'status':'RUNNING','stage':'Verified development training','metrics':[],'artifacts':[],'log':[],'acceptance':'Synthetic development only; independent final evidence is not reused for tuning.'};self.runs[rid]=r;self.save(r);threading.Thread(target=self.train,args=(r,),daemon=True).start();return {'id':rid}
 def train(self,r):
  try:
   d=self.root/r['id'];verified_training.run(self.data,d/'results')
   from verify_results_v05 import run as verify
   r['stage']='Verifying saved model predictions';self.save(r)
   verify(self.data,d/'results')
   result=json.loads((d/'results/evaluation.json').read_text());r['metrics']=[{'model':name,**m['classification'],'baseline_accuracy':m['no_churn_accuracy'],'top10':m['campaign_top10pct']} for name,m in result.items()]
   for name in result:
    r['stage']='Exporting calibrated serving model '+name;self.save(r)
    portable=d/'results'/(name+'_serving.joblib');parity=engine.export_model(d/'results'/(name+'.joblib'),self.data/'COM01_validation.csv',portable);(d/'results'/(name+'_serving_parity.json')).write_text(json.dumps(parity,indent=2))
   r['artifacts']=[{'name':p.name,'sha256':sha(p)} for p in sorted((d/'results').iterdir()) if p.is_file()];r.update(status='COMPLETED',stage='Four models, reload checks and calibrated serving exports completed')
  except Exception as e:
   r.update(status='FAILED',stage=type(e).__name__+': '+(str(e) or 'See diagnostic traceback below'))
   r.setdefault('log',[]).append(traceback.format_exc())
  self.save(r)
 def artifact(self,rid,name):
  r=self.runs.get(rid,{})
  entry=next((x for x in r.get('artifacts',[]) if x['name']==name),None)
  if not entry:raise ValueError('Unknown artifact')
  p=self.root/rid/'results'/name
  if sha(p)!=entry['sha256']:raise ValueError('Artifact checksum mismatch')
  return p
 def stage(self,rid,model):
  if model not in ['LR','XGB','CAT','LGBM']:raise ValueError('Unknown model')
  r=self.runs.get(rid,{})
  if r.get('status')!='COMPLETED':raise ValueError('Only completed verified runs can be staged')
  p=self.artifact(rid,model+'_serving.joblib');self.artifact(rid,model+'_serving_parity.json')
  settings=self.config.get('staging',{})
  if not settings.get('feature_sql'):raise ValueError('Configure reviewed engine Silver feature SQL before staging')
  m=next(x for x in r['metrics'] if x['model']==model)
  response=engine.push(p,settings['name'],settings['version'],settings['feature_sql'],{k:m[k] for k in ['roc_auc','accuracy']});r['staging']=response;self.save(r);return response

def serve(config,root,port):
 token=os.environ.get('COM01_RUNNER_TOKEN','')
 if not os.environ.get('COM01_RUNNER_TOKEN') or len(token)<24:raise ValueError('Set a random COM01_RUNNER_TOKEN of at least 24 characters')
 make_http_server(Admin(config,root),port,token).serve_forever()

def make_http_server(admin,port,token):
 sessions={};web=Path(__file__).parent.parent
 # Serve only known application assets, never configs, datasets or backend code.
 assets={'/'+name:name for name in [
  'training.js','training.css','styles.css','brief.css','brief.js',
  'business-report.css','business-report.js','data.js','app.js','demo-login.css',
  'demo-login.js','excel-export.js','report-dates.css','report-dates.js',
  'vendor/xlsx.mini.min.js','assets/atoma-logo.jpg']}
 assets['/login.js']='training_backend/login.js'
 class H(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def end_headers(self):
   self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'");super().end_headers()
  def send(self,data,status=200,kind='application/json'):
   body=json.dumps(data).encode() if kind=='application/json' else data;self.send_response(status);self.send_header('Content-Type',kind);self.end_headers();self.wfile.write(body)
  def valid_host(self):return self.headers.get('Host') in [f'127.0.0.1:{port}',f'localhost:{port}']
  def auth(self):
   cookie=SimpleCookie(self.headers.get('Cookie',''));s=cookie.get('com01_session');return bool(s and sessions.get(s.value,0)>time.time())
  def do_GET(self):
   if not self.valid_host():return self.send({'error':'Invalid host'},403)
   from urllib.parse import urlsplit
   path=urlsplit(self.path).path
   if path in ['/', '/index.html', '/training.html']:
    if not self.auth():return self.send((web/'training_backend/login.html').read_bytes(),kind='text/html')
    file='training.html' if path=='/training.html' else 'index.html'
    html=(web/file).read_text()
    if file=='index.html':html=html.replace('<body>','<body data-runner-session="true">',1)
    return self.send(html.encode(),kind='text/html')
   if path in assets:
    import mimetypes
    p=web/assets[path]
    if not p.is_file():return self.send({'error':'Asset not found'},404)
    return self.send(p.read_bytes(),kind=mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
   if not self.auth():return self.send({'error':'Unauthorised'},401)
   if self.path=='/api/session':return self.send({'authenticated':True,'mode':'development'})
   if self.path=='/api/status':return self.send(admin.status())
   if self.path.startswith('/api/artifacts/'):
    try:
     parts=self.path.split('/')
     if len(parts)!=5:raise ValueError('Invalid path')
     p=admin.artifact(*parts[3:]);return self.send(p.read_bytes(),kind='application/octet-stream')
    except Exception:return self.send({'error':'Unavailable artifact'},404)
   return self.send({'error':'Not found'},404)
  def do_POST(self):
   if not self.valid_host() or self.headers.get('Origin') not in [f'http://localhost:{port}',f'http://127.0.0.1:{port}']:return self.send({'error':'Same-origin request required'},403)
   n=int(self.headers.get('Content-Length','0'))
   if n>8192:return self.send({'error':'Request too large'},413)
   try:body=json.loads(self.rfile.read(n) or '{}')
   except Exception:return self.send({'error':'Invalid JSON'},400)
   if self.path=='/api/session':
    if not secrets.compare_digest(str(body.get('token','')),token):return self.send({'error':'Unauthorised'},401)
    sid=secrets.token_urlsafe(32);sessions[sid]=time.time()+8*3600;self.send_response(200);self.send_header('Set-Cookie',f'com01_session={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800');self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"ok":true}');return
   if not self.auth():return self.send({'error':'Unauthorised'},401)
   try:
    if self.path=='/api/logout':
     c=SimpleCookie(self.headers.get('Cookie',''));sessions.pop(c['com01_session'].value,None);return self.send({'ok':True})
    if self.path=='/api/runs':return self.send(admin.start(),202)
    if self.path=='/api/engine/connect':admin.connection=engine.connect();return self.send(admin.connection)
    if self.path=='/api/engine/stage':return self.send(admin.stage(body['run'],body['model']))
    return self.send({'error':'Not found'},404)
   except Exception as e:
    # Never echo SDK/server exceptions that could contain credentials.
    if self.path=='/api/engine/connect':
     setup=isinstance(e,engine.ConnectionSetupError)
     admin.connection={'status':'BLOCKED','code':e.code if setup else 'DEV_QUERY_FAILED','reason':str(e) if setup else 'Dev authentication or query failed. Check credential validity, gateway.query permission and network access.','query_check':'FAILED','production_publication_allowed':False}
     return self.send({'error':admin.connection['reason'],'connection':admin.connection},409)
    if self.path.startswith('/api/engine/'):
     admin.connection={'status':'BLOCKED','reason':'Check server credentials, SDK, scopes and reviewed Silver SQL'};return self.send({'error':admin.connection['reason']},409)
    return self.send({'error':str(e)},409)
 httpd=ThreadingHTTPServer(('127.0.0.1',port),H)
 port=httpd.server_address[1]
 return httpd
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--artifacts',default='local-artifacts');p.add_argument('--port',type=int,default=8765);a=p.parse_args();serve(a.config,a.artifacts,a.port)

