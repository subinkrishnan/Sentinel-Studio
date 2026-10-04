"""Independent diagnostic experiment. No canonical runner bypass or publication."""
from pathlib import Path
import argparse,hashlib,json,sys,platform
from datetime import datetime,timezone
import importlib.metadata
import numpy as np,pandas as pd,joblib
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score,average_precision_score,roc_auc_score,brier_score_loss,precision_recall_curve
FEATURES=['service_tenure_days','arpu_sgd','usage_data_mb_sum_30d','usage_data_mb_sum_prev30d','usage_data_mb_delta_30d_vs_prev30d','usage_active_days_count_30d','billing_overdue_amount_sgd','billing_payment_failure_count_90d','care_complaint_count_30d','care_repeat_contact_count_30d','network_incident_count_30d','network_degraded_minutes_30d','digital_active_days_count_30d','product_change_count_90d','contract_remaining_days']
CONTRACT='COM01_LOCAL_SYNTHETIC_15F_V05'

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def metrics(y,selected,p):
 tp=int(np.sum(selected&(y==1)));fp=int(np.sum(selected&(y==0)));fn=int(np.sum(~selected&(y==1)));tn=int(np.sum(~selected&(y==0)));prev=float(y.mean())
 return {'accuracy':float(accuracy_score(y,selected)),'precision':tp/max(tp+fp,1),'recall':tp/max(tp+fn,1),'lift':(tp/max(tp+fp,1))/prev,'pr_auc_average_precision':float(average_precision_score(y,p)),'roc_auc':float(roc_auc_score(y,p)),'brier':float(brier_score_loss(y,p)),'tp':tp,'fp':fp,'fn':fn,'tn':tn,'selected_count':tp+fp}

def probability(model,calibrator,frame):
 raw=np.clip(model.predict_proba(frame[FEATURES])[:,1],1e-6,1-1e-6)
 return calibrator.predict_proba(np.log(raw/(1-raw)).reshape(-1,1))[:,1]

def evaluate(frame,p,threshold):
 y=frame.label.to_numpy();selected=np.zeros(len(y),bool)
 for date in sorted(frame.data_as_of_ts.unique()):
  ix=np.flatnonzero((frame.data_as_of_ts==date).to_numpy());ranked=sorted(ix,key=lambda i:(-p[i],str(frame.iloc[i].training_observation_id)));selected[ranked[:int(np.ceil(len(ix)*.10))]]=True
 return {'observations':len(y),'positives':int(y.sum()),'prevalence':float(y.mean()),'no_churn_accuracy':float(1-y.mean()),'no_churn_brier':float(y.mean()),'constant_prevalence_brier_reference':float(y.mean()*(1-y.mean())),'classification_threshold':threshold,'classification':metrics(y,p>=threshold,p),'campaign_top10pct':metrics(y,selected,p),'mean_probability':float(p.mean())}

def preflight(data_dir):
 cfg=json.loads((data_dir/'dataset.json').read_text());assert cfg['feature_contract']==CONTRACT;report=json.loads((data_dir/'postgres_parity_report.json').read_text());review=json.loads((data_dir/'source_audit.json').read_text())
 if cfg['feature_corrections_verified'] is not True or cfg.get('local_training_only') is not True or cfg.get('production_approval') is not False:raise ValueError('Verified local-only candidate required')
 for name,digest in cfg['gate_evidence_sha256'].items():
  if sha(data_dir/name)!=digest:raise ValueError('Gate evidence changed: '+name)
 if json.loads((data_dir/'boundary_tests.json').read_text())['status']!='PASS':raise ValueError('Boundary tests failed')
 if sha(data_dir/'sql_inventory.json')!=cfg['source_sha256']:raise ValueError('Source inventory changed')
 for source in json.loads((data_dir/'sql_inventory.json').read_text())['sources']:
  if sha(data_dir/source['path'])!=source['sha256']:raise ValueError('Source export changed: '+source['name'])
 if report['status']!='PASS' or report['sql_label_audit']['mismatches']!=0 or review['status']!='PASS':raise ValueError('Diagnostic input checks failed')
 frames={}
 for role in ['train','validation']:
  path=data_dir/f'COM01_{role}.csv'
  if sha(path)!=cfg[role]['sha256']:raise ValueError(role+' hash mismatch')
  df=pd.read_csv(path);df.data_as_of_ts=pd.to_datetime(df.data_as_of_ts,utc=True);df.label_matured_ts=pd.to_datetime(df.label_matured_ts,utc=True)
  if df.empty or not df.label.isin([0,1]).all() or df.label.nunique()!=2 or not df.training_observation_id.is_unique:raise ValueError('Invalid supervised observations')
  if not (df.label_matured_ts==df.data_as_of_ts+pd.Timedelta(days=30)).all():raise ValueError('Label maturity invalid')
  if df[FEATURES].isna().any().any() or not np.isfinite(df[FEATURES].to_numpy()).all():raise ValueError('Diagnostic features missing/nonfinite')
  frames[role]=df
 held_path=data_dir/'reserved_service_ids.json'
 if sha(held_path)!=cfg['heldout_service_ids']['sha256']:raise ValueError('Reservation hash mismatch')
 held=set(json.loads(held_path.read_text()))
 if len(held)!=2000 or any(set(d.service_instance_id)&held for d in frames.values()):raise ValueError('Reserved population violation')
 train=frames['train'];val=frames['validation'].reset_index(drop=True)
 if set(train.training_observation_id)&set(val.training_observation_id) or train.label_matured_ts.max()>val.data_as_of_ts.min():raise ValueError('Split violation')
 cutoff=train.data_as_of_ts.max();fit=train[train.label_matured_ts<=cutoff];cal=train[train.data_as_of_ts==cutoff].reset_index(drop=True)
 if set(fit.training_observation_id)&set(cal.training_observation_id) or fit.label.nunique()!=2 or cal.label.nunique()!=2:raise ValueError('Calibration split violation')
 return cfg,frames,held,fit,cal

def run(data_dir,output):
 if output.exists():raise FileExistsError('Use a new output directory; existing experiment is preserved')
 cfg,frames,held,fit,cal=preflight(data_dir);train=frames['train'];val=frames['validation'].reset_index(drop=True);cutoff=train.data_as_of_ts.max()
 from xgboost import XGBClassifier
 from catboost import CatBoostClassifier
 from lightgbm import LGBMClassifier
 estimators={'LR':LogisticRegression(max_iter=1500,class_weight='balanced',random_state=42),'XGB':XGBClassifier(n_estimators=200,max_depth=3,learning_rate=.05,random_state=42,n_jobs=2),'CAT':CatBoostClassifier(iterations=200,depth=4,verbose=False,random_seed=42,thread_count=2),'LGBM':LGBMClassifier(n_estimators=200,max_depth=4,random_state=42,n_jobs=2,verbosity=-1)}
 output.mkdir(parents=True);results={};summaries=[]
 for name,est in estimators.items():
  print('Training corrected local candidate',name,flush=True)
  model=make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),est);model.fit(fit[FEATURES],fit.label)
  raw=np.clip(model.predict_proba(cal[FEATURES])[:,1],1e-6,1-1e-6);logits=np.log(raw/(1-raw)).reshape(-1,1);calibrator=LogisticRegression(C=1e6).fit(logits,cal.label)
  cp=probability(model,calibrator,cal);prec,rec,thresholds=precision_recall_curve(cal.label,cp);f1=2*prec[:-1]*rec[:-1]/np.maximum(prec[:-1]+rec[:-1],1e-15);chosen=int(np.argmax(f1));threshold=float(thresholds[chosen])
  vp=probability(model,calibrator,val);evaluation=evaluate(val,vp,threshold);evaluation['raw_validation_auc']=float(roc_auc_score(val.label,model.predict_proba(val[FEATURES])[:,1]));evaluation['raw_validation_ap']=float(average_precision_score(val.label,model.predict_proba(val[FEATURES])[:,1]));evaluation['constant_calibration_prevalence_brier']=float(brier_score_loss(val.label,np.full(len(val),cal.label.mean())));evaluation['threshold_selected_on']='last training-date calibration slice only; maximum F1';evaluation['calibration_threshold_f1']=float(f1[chosen]);evaluation['sigmoid_coefficient']=float(calibrator.coef_[0,0]);evaluation['by_date']={str(day):evaluate(val.loc[val.data_as_of_ts==day].reset_index(drop=True),vp[(val.data_as_of_ts==day).to_numpy()],threshold) for day in sorted(val.data_as_of_ts.unique())};results[name]=evaluation
  joblib.dump({'feature_contract':CONTRACT,'features':FEATURES,'excluded_features':[],'model':model,'calibrator':calibrator,'classification_threshold':threshold,'purpose':'local_synthetic_experiment_only','publication_allowed':False},output/f'{name}.joblib')
  pred=val[['training_observation_id','service_instance_id','data_as_of_ts','label']].copy();pred['probability']=vp;pred['threshold']=threshold;pred['predicted_label']=(vp>=threshold).astype(int);temporary=output/f'{name}_predictions.building';pred.to_csv(temporary,index=False);temporary.replace(output/f'{name}_validation_predictions.csv')
  summaries.append({'model':name,'pr_auc':evaluation['classification']['pr_auc_average_precision'],'roc_auc':evaluation['classification']['roc_auc'],'classification_accuracy':evaluation['classification']['accuracy'],'classification_precision':evaluation['classification']['precision'],'classification_recall':evaluation['classification']['recall'],'top10_precision':evaluation['campaign_top10pct']['precision'],'top10_recall':evaluation['campaign_top10pct']['recall'],'top10_lift':evaluation['campaign_top10pct']['lift'],'brier':evaluation['classification']['brier'],'threshold':threshold,'no_churn_accuracy':evaluation['no_churn_accuracy']})
  print(name,json.dumps(summaries[-1]),flush=True)
 pd.DataFrame(summaries).to_csv(output/'metrics.csv',index=False)
 manifest={'status':'LOCAL_15F_TRAINING_COMPLETED','feature_contract':CONTRACT,'features':FEATURES,'excluded_features':{},'source_manifest_sha256':cfg['source_manifest_sha256'],'validation_reused_during_development':False,'benchmark_spec_sha256':sha(data_dir/'benchmark_spec_frozen.json'),'training_script_sha256':sha(Path(__file__)),'production_business_approval':False,'source_sha256':cfg['source_sha256'],'split_sha256':{role:cfg[role]['sha256'] for role in frames},'fit_observations':len(fit),'calibration_observations':len(cal),'validation_observations':len(val),'fit_label_maturity_max':str(fit.label_matured_ts.max()),'calibration_cutoff':str(cutoff),'threshold_selection':'Calibration-only maximum F1; fixed before validation evaluation','campaign_policy':'Top 10 percent separately within each validation date; deterministic observation-ID tie break','reserved_services_excluded':len(held),'oot_evaluated':False,'blind_scored':False,'canonical_com01_training_authorised':False,'gold_publication_allowed':False,'production_etl_completeness_attested':False,'python':platform.python_version(),'versions':{n:importlib.metadata.version(n) for n in ['numpy','pandas','scikit-learn','xgboost','catboost','lightgbm','joblib']},'created_utc':datetime.now(timezone.utc).isoformat()}
 (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(output/'evaluation.json').write_text(json.dumps(results,indent=2)+'\n')
 (output/'checksums.json').write_text(json.dumps({p.name:sha(p) for p in output.iterdir() if p.is_file()},indent=2)+'\n')
 print('Source-first benchmark training completed. Production approval and Gold publication remain blocked.',flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.data_dir.expanduser().resolve(),args.output.expanduser().resolve())
