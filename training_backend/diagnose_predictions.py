"""Read-only saved prediction diagnostic. Does not change gates, files or models."""
import argparse,json,platform,importlib.metadata
from pathlib import Path
import joblib,numpy as np,pandas as pd
from verified_training import sha,probability,evaluate

def diagnose(data,results):
 checks=json.loads((results/'checksums.json').read_text());manifest=json.loads((results/'manifest.json').read_text())
 bad=[name for name,digest in checks.items() if sha(results/name)!=digest]
 if bad:raise ValueError('Result checksum mismatch: '+', '.join(bad))
 if sha(data/'COM01_validation.csv')!=manifest['split_sha256']['validation']:raise ValueError('Validation data checksum mismatch')
 frame=pd.read_csv(data/'COM01_validation.csv');frame.data_as_of_ts=pd.to_datetime(frame.data_as_of_ts,utc=True);evaluations=json.loads((results/'evaluation.json').read_text())
 report={'python':platform.python_version(),'versions':{n:importlib.metadata.version(n) for n in ['numpy','pandas','scikit-learn','xgboost','catboost','lightgbm','joblib']},'saved_versions':manifest['versions'],'artifact_hashes_match':True,'validation_hash_matches':True,'models':{}}
 for name in ['LR','XGB','CAT','LGBM']:
  a=joblib.load(results/(name+'.joblib'));saved=pd.read_csv(results/(name+'_validation_predictions.csv'),float_precision='round_trip')
  if not saved.training_observation_id.equals(frame.training_observation_id) or not saved.label.equals(frame.label):raise ValueError(name+' observation/label identity mismatch')
  p=probability(a['model'],a['calibrator'],frame);q=saved.probability.to_numpy();original_csv=pd.read_csv(results/(name+'_validation_predictions.csv')).probability.to_numpy();diff=np.abs(p.astype(np.float64)-q);cast=q.astype(p.dtype);threshold=a['classification_threshold'];actual=evaluate(frame,p,threshold);expected=evaluations[name]
  report['models'][name]={'reloaded_probability_dtype':str(p.dtype),'calibrator_coefficient_dtype':str(a['calibrator'].coef_.dtype),'strict_original_check_passes':bool(np.allclose(p,original_csv,rtol=1e-12,atol=1e-12)),'strict_roundtrip_parser_check_passes':bool(np.allclose(p,q,rtol=1e-12,atol=1e-12)),'max_absolute_probability_difference':float(diff.max()),'mean_absolute_probability_difference':float(diff.mean()),'csv_restored_to_reloaded_dtype_matches_exactly':bool(np.array_equal(p,cast)),'changed_frozen_threshold_decisions':int(np.sum((p>=threshold).astype(int)!=saved.predicted_label.to_numpy())),'top10_true_positives_match':actual['campaign_top10pct']['tp']==expected['campaign_top10pct']['tp'],'roc_auc_difference':actual['classification']['roc_auc']-expected['classification']['roc_auc'],'average_precision_difference':actual['classification']['pr_auc_average_precision']-expected['classification']['pr_auc_average_precision']}
 return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--runs',type=Path,required=True);a=p.parse_args();latest=max(a.runs.glob('*/run.json'),key=lambda x:x.stat().st_mtime);print('Run:',latest.parent.name);print(json.dumps(diagnose(a.data_dir,latest.parent/'results'),indent=2))
