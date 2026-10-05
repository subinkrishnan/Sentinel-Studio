"""Server-only Sentinel SDK bridge. Staging push only; never promotes or publishes."""
import os
from pathlib import Path
from urllib.parse import urlsplit

class ConnectionSetupError(ValueError):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code = code

def client():
    url=os.environ.get('SENTINEL_BASE_URL','https://dev.sentinel.inalpha.ai')
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname!='dev.sentinel.inalpha.ai' or parsed.username or parsed.password or parsed.query:
        raise ConnectionSetupError('INVALID_DEV_ORIGIN','Only the Sentinel Dev HTTPS origin is supported; check SENTINEL_BASE_URL')
    cid=os.environ.get('SENTINEL_CLIENT_ID','').strip().removeprefix('client_id=').strip();secret=os.environ.get('SENTINEL_CLIENT_SECRET','').strip().removeprefix('client_secret=').strip()
    if not cid or not secret:
        missing = ', '.join(name for name, value in [('SENTINEL_CLIENT_ID', cid), ('SENTINEL_CLIENT_SECRET', secret)] if not value)
        raise ConnectionSetupError('MISSING_CREDENTIALS','Sentinel client credentials missing from the Studio service environment: ' + missing + '. The Studio login token is separate.')
    try:
        from sentinel_client import Client
    except ImportError as error:
        code = 'SDK_NOT_INSTALLED' if getattr(error, 'name', None) == 'sentinel_client' else 'SDK_IMPORT_FAILED'
        raise ConnectionSetupError(code,'Sentinel SDK could not be loaded in the Studio Python environment. Use the environment containing the working uploader SDK.') from None
    return Client(url,cid,secret)

def connect():
    # No customer data is read; authentication/scopes are exercised by the SDK.
    result=client().query('SELECT 1 AS ok')
    if result!=[{'ok':1}]:raise ConnectionSetupError('QUERY_RESPONSE_MISMATCH','Dev returned an unexpected result for the connectivity query SELECT 1 AS ok')
    return {'status':'CONNECTED','query_check':'PASS','production_publication_allowed':False}

def portable_model(artifact):
    import numpy as np
    from scipy.special import logit
    from sklearn.ensemble import StackingClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import FunctionTransformer
    # Standard library/package classes only: no bespoke class required on Sentinel.
    model=StackingClassifier(estimators=[('base',artifact['model'])],cv='prefit')
    model.estimators_=[artifact['model']];model.stack_method_=['predict_proba'];model.classes_=np.array([0,1]);model._label_encoder=__import__('sklearn.preprocessing',fromlist=['LabelEncoder']).LabelEncoder().fit([0,1])
    model.final_estimator_=make_pipeline(FunctionTransformer(np.clip,kw_args={'a_min':1e-6,'a_max':1-1e-6}),FunctionTransformer(logit),artifact['calibrator'])
    return model

def export_model(artifact_path,validation_path,dest):
    import joblib,numpy as np,pandas as pd
    from verified_training import probability
    artifact=joblib.load(artifact_path);frame=pd.read_csv(validation_path);model=portable_model(artifact)
    joblib.dump(model,dest);restored=joblib.load(dest)
    expected=probability(artifact['model'],artifact['calibrator'],frame)
    actual=restored.predict_proba(frame[artifact['features']])[:,1]
    if not np.allclose(expected,actual,rtol=0,atol=1e-7):
        Path(dest).unlink(missing_ok=True);raise ValueError('Portable serving probabilities differ from the calibrated training artifact')
    if not np.array_equal(expected>=artifact['classification_threshold'],actual>=artifact['classification_threshold']):raise ValueError('Serving export changed frozen-threshold decisions')
    return {'status':'LOCAL_PARITY_PASS','absolute_probability_tolerance':1e-7,'frozen_threshold_decisions_match':True,'engine_must_return':'positive-class probability; threshold applied separately','observations':len(frame),'max_probability_difference':float(np.max(np.abs(expected-actual))),'engine_runtime_parity':'PENDING'}

def push(path,name,version,sql,metrics):
    import re
    if not re.fullmatch(r'com01_experiment_[a-z0-9_]+',name):raise ValueError('Use a separate com01_experiment_ model name')
    if not re.fullmatch(r'v\d+\.\d+\.\d+',version):raise ValueError('Version must be vN.N.N')
    if not sql or 'silver__' not in sql.lower():raise ValueError('Configure the reviewed Silver feature query; local fixture SQL is not a deployed mart')
    # The platform API authenticates, verifies, signs and lands in STAGING.
    result=client().push_model(name=name,version=version,artifact_path=str(path),feature_sql=sql,framework='sklearn',evaluation_metrics=metrics)
    return {'status':'STAGING_PUSH_SUBMITTED','response':result,'engine_runtime_parity':'PENDING_LIVE_TEST','production_publication_allowed':False}

