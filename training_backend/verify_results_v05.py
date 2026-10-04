from pathlib import Path
import argparse,json,hashlib,importlib.util
import pandas as pd,numpy as np,joblib
from sklearn.metrics import roc_auc_score,average_precision_score

def run(data_dir,results):
 spec=importlib.util.spec_from_file_location('diagnostic',Path(__file__).with_name('verified_training.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 manifest=json.loads((results/'manifest.json').read_text());checks=json.loads((results/'checksums.json').read_text());val=pd.read_csv(data_dir/'COM01_validation.csv');val.data_as_of_ts=pd.to_datetime(val.data_as_of_ts,utc=True)
 for name,digest in checks.items():assert m.sha(results/name)==digest
 assert m.sha(data_dir/'COM01_validation.csv')==manifest['split_sha256']['validation']
 rng=np.random.default_rng(20261004);random_tp=np.zeros(200000,dtype=int)
 for day,g in val.groupby('data_as_of_ts'):
  random_tp+=rng.hypergeometric(int(g.label.sum()),len(g)-int(g.label.sum()),int(np.ceil(len(g)*.1)),len(random_tp))
 evaluation=json.loads((results/'evaluation.json').read_text());audit={}
 for name in ['LR','XGB','CAT','LGBM']:
  artifact=joblib.load(results/(name+'.joblib'));assert artifact['features']==m.FEATURES and artifact['feature_contract']==m.CONTRACT and artifact['publication_allowed'] is False
  p=m.probability(artifact['model'],artifact['calibrator'],val);pred=pd.read_csv(results/(name+'_validation_predictions.csv'))
  assert pred.training_observation_id.equals(val.training_observation_id) and pred.label.equals(val.label)
  assert np.allclose(p,pred.probability,rtol=1e-12,atol=1e-12)
  assert np.array_equal((p>=artifact['classification_threshold']).astype(int),pred.predicted_label)
  actual=m.evaluate(val,p,artifact['classification_threshold']);expected=evaluation[name]
  assert np.isclose(actual['classification']['roc_auc'],expected['classification']['roc_auc']) and np.isclose(actual['classification']['pr_auc_average_precision'],expected['classification']['pr_auc_average_precision'])
  assert actual['campaign_top10pct']['tp']==expected['campaign_top10pct']['tp']
  tp=actual['campaign_top10pct']['tp'];pvalue=float((1+np.sum(random_tp>=tp))/(len(random_tp)+1))
  audit[name]={'persisted_model_predictions_reproduced':True,'roc_auc':actual['classification']['roc_auc'],'pr_auc':actual['classification']['pr_auc_average_precision'],'top10_true_positives':tp,'top10_random_selection_one_sided_pvalue':pvalue,'bonferroni_adjusted_pvalue_4_models':min(1.,pvalue*4),'sigmoid_calibration_coefficient':expected['sigmoid_coefficient']}
 report={'status':'PASS','artifact_hashes_match':True,'models':audit,'random_selection_test':'200,000 draws under a per-date hypergeometric null; fixed observed class totals and top10% sample sizes. Exploratory only; repeated-service dependence is not modeled.','random_selection_tp_95pct_interval':[int(x) for x in np.quantile(random_tp,[.025,.975])],'significant_top10_improvement_any_model_at_5pct_after_4_tests':any(x['bonferroni_adjusted_pvalue_4_models']<.05 for x in audit.values()),'model_qualification':'NOT_QUALIFIED','blind_or_reserved_evaluated':False}
 (results/'result_verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--results',type=Path,required=True);a=p.parse_args();run(a.data_dir,a.results)
