"""Local development runner. No engine writes, OOT evaluation or blind scoring."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import traceback
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FEATURES = ['service_tenure_days','arpu_sgd','usage_data_mb_sum_30d','usage_data_mb_sum_prev30d','usage_data_mb_delta_30d_vs_prev30d','usage_active_days_count_30d','billing_overdue_amount_sgd','billing_payment_failure_count_90d','care_complaint_count_30d','care_repeat_contact_count_30d','network_incident_count_30d','network_degraded_minutes_30d','digital_active_days_count_30d','product_change_count_90d','contract_remaining_days']

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def load_dataset(config_path):
    import numpy as np
    import pandas as pd
    cfg=json.loads(Path(config_path).read_text())
    if cfg.get('purpose')!='historical_development': raise ValueError('Only historical development data is allowed')
    if cfg.get('feature_corrections_verified') is not True:
        raise ValueError('Correct feature availability and verify Python/SQL parity before training')
    if not cfg.get('evidence_reference'): raise ValueError('A feature correction/parity evidence reference is required')
    if sha(cfg['source_path'])!=cfg['source_sha256']: raise ValueError('Historical source checksum mismatch')
    frames={}
    inventory={'source_sha256':cfg['source_sha256'],'feature_evidence':cfg['evidence_reference'],'purpose':cfg['purpose']}
    for split in ['train','validation']:
        entry=cfg[split]; path=Path(entry['path']).resolve()
        if sha(path)!=entry['sha256']: raise ValueError(split+' checksum mismatch')
        df=pd.read_csv(path)
        required=FEATURES+['label','data_as_of_ts','training_observation_id','service_instance_id']
        if not set(required)<=set(df.columns): raise ValueError(split+' required columns missing')
        if df.empty or not df.label.isin([0,1]).all() or df.label.nunique()!=2: raise ValueError(split+' needs mature binary labels with both classes')
        if df.training_observation_id.isna().any() or df.training_observation_id.duplicated().any(): raise ValueError(split+' observation IDs missing or duplicated')
        if df.service_instance_id.isna().any(): raise ValueError(split+' service IDs missing')
        df['data_as_of_ts']=pd.to_datetime(df.data_as_of_ts,utc=True,errors='raise')
        if df.data_as_of_ts.isna().any(): raise ValueError(split+' dates missing')
        for col in FEATURES:
            df[col]=pd.to_numeric(df[col],errors='raise')
            cap=.60 if col=='contract_remaining_days' else .30
            if df[col].isna().mean()>cap or np.isinf(df[col]).any(): raise ValueError(split+' invalid feature coverage: '+col)
        inventory[split]={'observations':len(df),'services':int(df.service_instance_id.nunique()),'positives':int(df.label.sum()),'sha256':entry['sha256'],'first_date':str(df.data_as_of_ts.min()),'last_date':str(df.data_as_of_ts.max())}
        frames[split]=df
    if set(frames['train'].training_observation_id)&set(frames['validation'].training_observation_id): raise ValueError('Train/validation observation overlap')
    if pd.Timestamp(frames['train'].data_as_of_ts.max())+pd.Timedelta(days=30)>pd.Timestamp(frames['validation'].data_as_of_ts.min()): raise ValueError('Training labels do not mature before validation cutoff')
    # Held-out service membership must be supplied separately, never inferred from OOT features or truth.
    held=cfg.get('heldout_service_ids')
    if not held: raise ValueError('Provide reserved-service exclusion manifest')
    if sha(held['path'])!=held['sha256']: raise ValueError('Held-out exclusion manifest checksum mismatch')
    reserved=set(json.loads(Path(held['path']).read_text()))
    if not reserved: raise ValueError('Reserved service manifest is empty')
    if any(set(df.service_instance_id)&reserved for df in frames.values()): raise ValueError('Reserved OOT services appear in development data')
    inventory['reserved_services_excluded']=len(reserved)
    return frames, inventory

def evaluate(model,period,frame,p):
    import numpy as np
    from sklearn.metrics import accuracy_score,average_precision_score,brier_score_loss,roc_auc_score
    y=frame.label.to_numpy(); selected=np.zeros(len(y),dtype=bool)
    # Match the per-date action policy, including deterministic tie-breaking.
    for date in sorted(frame.data_as_of_ts.unique()):
        idx=np.flatnonzero((frame.data_as_of_ts==date).to_numpy())
        ordered=sorted(idx,key=lambda i:(-p[i],str(frame.iloc[i].training_observation_id)))
        selected[ordered[:int(np.ceil(len(idx)*.10))]]=True
    tp=int(np.sum(selected&(y==1))); fp=int(np.sum(selected&(y==0))); fn=int(np.sum(~selected&(y==1))); tn=int(np.sum(~selected&(y==0)))
    precision=tp/max(tp+fp,1); prevalence=float(y.mean())
    return {'model':model,'period':period,'observations':len(y),'accuracy':float(accuracy_score(y,selected)),'baseline_accuracy':1-prevalence,'precision':precision,'recall':tp/max(tp+fn,1),'lift':precision/prevalence if prevalence else 0,'pr_auc':float(average_precision_score(y,p)) if prevalence else 0,'roc_auc':float(roc_auc_score(y,p)) if len(set(y))==2 else None,'brier':float(brier_score_loss(y,p)),'tp':tp,'fp':fp,'fn':fn,'tn':tn}

class Runner:
    def __init__(self,config,root):
        self.config=config; self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock(); self.runs={}; self.dataset=None; self.dataset_error=None
        try: _,self.dataset=load_dataset(config)
        except Exception as e: self.dataset_error=str(e)
        for path in self.root.glob('*/run.json'):
            r=json.loads(path.read_text())
            if r['status']=='RUNNING': r.update(status='FAILED',stage='Interrupted; start a new development run')
            self.runs[r['id']]=r
    def persist(self,r):
        with self.lock:
            dest=self.root/r['id'];dest.mkdir(exist_ok=True)
            tmp=dest/'run.tmp';tmp.write_text(json.dumps(r,indent=2));tmp.replace(dest/'run.json')
    def status(self):
        with self.lock: return {'dataset':self.dataset,'dataset_error':self.dataset_error,'runs':list(self.runs.values())[::-1]}
    def start(self):
        with self.lock:
            if any(r['status']=='RUNNING' for r in self.runs.values()): raise ValueError('A run is already running')
            frames,inventory=load_dataset(self.config);self.dataset=inventory
            rid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
            r={'id':rid,'status':'RUNNING','stage':'Preparing calibration split','log':[],'metrics':[],'artifacts':[],'acceptance':'Development only; model qualification, OOT and Gold publication are pending.'}
            self.runs[rid]=r;self.persist(r)
            threading.Thread(target=self.train,args=(r,frames,inventory),daemon=True).start()
            return {'id':rid}
    def train(self,r,frames,inventory):
        try:
            import joblib
            import numpy as np
            import pandas as pd
            import sklearn
            from sklearn.impute import SimpleImputer
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import make_pipeline
            from sklearn.linear_model import LogisticRegression
            train=frames['train'];val=frames['validation'].reset_index(drop=True)
            cutoff=train.data_as_of_ts.max();fit=train[train.data_as_of_ts+pd.Timedelta(days=30)<=cutoff];cal=train[train.data_as_of_ts==cutoff]
            if fit.label.nunique()!=2 or cal.label.nunique()!=2: raise ValueError('Insufficient classes in purged fit/calibration split')
            estimators={'LR':LogisticRegression(max_iter=1500,class_weight='balanced',random_state=42)}
            try:
                from xgboost import XGBClassifier
                estimators['XGB']=XGBClassifier(n_estimators=200,max_depth=3,learning_rate=.05,random_state=42,n_jobs=2)
            except ImportError: r['log'].append('XGB unavailable: install requirements')
            try:
                from catboost import CatBoostClassifier
                estimators['CAT']=CatBoostClassifier(iterations=200,depth=4,verbose=False,random_seed=42,thread_count=2)
            except ImportError: r['log'].append('CAT unavailable: install requirements')
            try:
                from lightgbm import LGBMClassifier
                estimators['LGBM']=LGBMClassifier(n_estimators=200,max_depth=4,random_state=42,n_jobs=2,verbosity=-1)
            except ImportError: r['log'].append('LGBM unavailable: install requirements')
            dest=self.root/r['id']
            for name,est in estimators.items():
                r['stage']='Training '+name;self.persist(r)
                model=make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),est)
                model.fit(fit[FEATURES],fit.label)
                # Fit a sigmoid calibrator on a later, purged development slice only.
                raw=np.clip(model.predict_proba(cal[FEATURES])[:,1],1e-6,1-1e-6)
                calibrator=LogisticRegression(C=1e6).fit(np.log(raw/(1-raw)).reshape(-1,1),cal.label)
                raw=np.clip(model.predict_proba(val[FEATURES])[:,1],1e-6,1-1e-6)
                p=calibrator.predict_proba(np.log(raw/(1-raw)).reshape(-1,1))[:,1]
                r['metrics'].append(evaluate(name,'ALL',val,p))
                for day in sorted(val.data_as_of_ts.unique()):
                    mask=(val.data_as_of_ts==day).to_numpy()
                    r['metrics'].append(evaluate(name,str(day),val.loc[mask].reset_index(drop=True),p[mask]))
                joblib.dump({'model':model,'calibrator':calibrator,'features':FEATURES,'purpose':'development_only'},dest/(name+'.joblib'))
                r['log'].append(name+' fitted and evaluated; no champion approval inferred');self.persist(r)
            pd.DataFrame(r['metrics']).to_csv(dest/'metrics.csv',index=False)
            (dest/'manifest.json').write_text(json.dumps({'dataset':inventory,'features':FEATURES,'action_budget':.10,'fit_rows':len(fit),'calibration_rows':len(cal),'versions':{'sklearn':sklearn.__version__,'pandas':pd.__version__,'numpy':np.__version__},'oot_evaluated':False,'blind_scored':False,'status':'DEVELOPMENT_ONLY'},indent=2))
            for path in sorted(dest.iterdir()):
                if path.name not in ['run.json','run.tmp']: r['artifacts'].append({'name':path.name,'sha256':sha(path)})
            r.update(status='COMPLETED',stage='Development metrics recorded. Acceptance remains pending.')
        except Exception as e:
            r.update(status='FAILED',stage=str(e));r['log'].append(traceback.format_exc())
        self.persist(r)

def serve(config,root,port):
    token=os.environ.get('COM01_RUNNER_TOKEN')
    if not token or len(token)<24: raise ValueError('Set COM01_RUNNER_TOKEN to at least 24 random characters')
    runner=Runner(config,root); web=Path(__file__).resolve().parent.parent
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def end_headers(self):
            origin=self.headers.get('Origin','')
            if origin in [f'http://127.0.0.1:{port}',f'http://localhost:{port}','https://subinkrishnan.github.io']:
                self.send_header('Access-Control-Allow-Origin',origin)
                self.send_header('Vary','Origin')
            self.send_header('Cache-Control','no-store');super().end_headers()
        def json(self,data,status=200):
            body=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
        def authorized(self): return secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+token)
        def do_OPTIONS(self):
            self.send_response(204);self.send_header('Access-Control-Allow-Headers','Authorization,Content-Type');self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS');self.end_headers()
        def do_GET(self):
            if self.path.startswith('/api/'):
                if not self.authorized(): return self.json({'error':'Unauthorised'},401)
                if self.path=='/api/status': return self.json(runner.status())
                if self.path.startswith('/api/artifacts/'):
                    parts=self.path.split('/')
                    if len(parts)!=5: return self.json({'error':'Invalid artifact'},404)
                    rid,name=parts[3:];r=runner.runs.get(rid,{})
                    if name not in [a['name'] for a in r.get('artifacts',[])]: return self.json({'error':'Unknown artifact'},404)
                    path=runner.root/rid/name
                    self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Disposition','attachment; filename="'+name+'"');self.end_headers();self.wfile.write(path.read_bytes());return
                return self.json({'error':'Unsupported API'},404)
            allowed={'/':'training.html','/training.html':'training.html','/training.js':'training.js','/training.css':'training.css','/styles.css':'styles.css'}
            name=allowed.get(self.path)
            if not name:return self.json({'error':'Not found'},404)
            self.send_response(200);self.send_header('Content-Type',{'html':'text/html','css':'text/css','js':'text/javascript'}[name.split('.')[-1]]);self.end_headers();self.wfile.write((web/name).read_bytes())
        def do_POST(self):
            if not self.authorized():return self.json({'error':'Unauthorised'},401)
            if self.path!='/api/runs':return self.json({'error':'Unsupported API'},404)
            try:self.json(runner.start(),202)
            except Exception as e:self.json({'error':str(e)},409)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--artifacts',default='local-artifacts');parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args();serve(args.config,args.artifacts,args.port)
