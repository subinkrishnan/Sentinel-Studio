"""Verify and finish an existing failed local run; never fits or tunes a model."""
import argparse,json,tempfile,shutil,socket
from pathlib import Path
from datetime import datetime,timezone
from server import sha
from verify_results_v05 import run as verify
from engine import export_model

def recover(config,runs,rid,port=8767):
 with socket.socket() as sock:
  if sock.connect_ex(('127.0.0.1',port))==0:raise ValueError('Stop the admin server with Control+C before recovery')
 for p in runs.glob('*/run.json'):
  if json.loads(p.read_text()).get('status')=='RUNNING':raise ValueError('An active run exists; recovery is blocked')
 if Path(rid).name!=rid:raise ValueError('Invalid run ID')
 d=runs/rid;path=d/'run.json';record=json.loads(path.read_text());results=d/'results';data=Path(json.loads(config.read_text())['data_dir']).expanduser()
 if record['status']!='FAILED':raise ValueError('Recover only a failed run')
 for model in ['LR','XGB','CAT','LGBM']:
  if (results/(model+'_serving.joblib')).exists():raise ValueError('Serving export already exists; preserve and review partial recovery')
 backup=d/'run.before_precision_recovery.json'
 if backup.exists():raise ValueError('Recovery evidence already exists; review before retry')
 # Verification checks original hashes, identities, decisions and metrics.
 verify(data,results)
 evaluation=json.loads((results/'evaluation.json').read_text());parities={}
 with tempfile.TemporaryDirectory(prefix='serving-recovery-',dir=d) as tmp:
  temp=Path(tmp)
  for model in ['LR','XGB','CAT','LGBM']:
   parities[model]=export_model(results/(model+'.joblib'),data/'COM01_validation.csv',temp/(model+'_serving.joblib'))
   (temp/(model+'_serving_parity.json')).write_text(json.dumps(parities[model],indent=2))
  shutil.copy2(path,backup)
  for p in temp.iterdir():p.replace(results/p.name)
 evidence={'status':'PASS','recovered_utc':datetime.now(timezone.utc).isoformat(),'original_run_state_sha256':sha(backup),'no_retraining':True,'no_threshold_or_calibration_changes':True,'original_models_and_prediction_csvs_unchanged':True,'serving_parity':parities,'production_publication_allowed':False}
 (results/'precision_recovery.json').write_text(json.dumps(evidence,indent=2))
 record['metrics']=[{'model':name,**m['classification'],'baseline_accuracy':m['no_churn_accuracy'],'top10':m['campaign_top10pct']} for name,m in evaluation.items()]
 record['artifacts']=[{'name':p.name,'sha256':sha(p)} for p in sorted(results.iterdir()) if p.is_file()]
 record.setdefault('log',[]).append('CSV native-precision verification passed; original fitted models, thresholds and prediction files preserved. Serving exports passed local parity. No engine writes.')
 record.update(status='COMPLETED',stage='Existing run verified and recovered; all four serving exports passed local checks')
 out=d/'run.recovered.tmp';out.write_text(json.dumps(record,indent=2));out.replace(path)
 print('RECOVERY: COMPLETED');print('Run:',rid);print('Original fitted models and thresholds preserved. No retraining. Sentinel engine connection remains pending.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--runs',type=Path,required=True);p.add_argument('--run-id',required=True);p.add_argument('--port',type=int,default=8767);a=p.parse_args();recover(a.config,a.runs,a.run_id,a.port)
