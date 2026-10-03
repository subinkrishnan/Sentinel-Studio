import unittest
import tempfile
from pathlib import Path
import json
import pandas as pd
import numpy as np
from server import load_dataset, evaluate, sha, FEATURES

class RunnerChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        source=self.root/'source.zip';source.write_bytes(b'test fixture, not a production dataset')
        held=self.root/'held.json';held.write_text(json.dumps(['RESERVED']))
        self.cfg={'purpose':'historical_development','feature_corrections_verified':True,'evidence_reference':'test fixture evidence','source_path':str(source),'source_sha256':sha(source),'heldout_service_ids':{'path':str(held),'sha256':sha(held)}}
        for name,day in [('train','2025-01-01'),('validation','2025-03-01')]:
            df=pd.DataFrame({f:[1.,2.,3.,4.] for f in FEATURES})
            df['label']=[0,1,0,1];df['service_instance_id']=['A','B','C','D'];df['training_observation_id']=[name+str(i) for i in range(4)];df['data_as_of_ts']=day
            path=self.root/(name+'.csv');df.to_csv(path,index=False);self.cfg[name]={'path':str(path),'sha256':sha(path)}
        self.path=self.root/'config.json';self.save()
    def save(self):self.path.write_text(json.dumps(self.cfg))
    def test_verified_development_asset(self):
        frames,inventory=load_dataset(self.path);self.assertEqual(inventory['train']['observations'],4)
    def test_blind_rejected(self):
        self.cfg['purpose']='blind';self.save()
        with self.assertRaisesRegex(ValueError,'historical'):load_dataset(self.path)
    def test_unverified_features_rejected(self):
        self.cfg['feature_corrections_verified']=False;self.save()
        with self.assertRaisesRegex(ValueError,'Correct feature'):load_dataset(self.path)
    def test_checksum_rejected(self):
        self.cfg['train']['sha256']='wrong';self.save()
        with self.assertRaisesRegex(ValueError,'checksum'):load_dataset(self.path)
    def test_reserved_services_rejected(self):
        held=Path(self.cfg['heldout_service_ids']['path']);held.write_text('["A"]');self.cfg['heldout_service_ids']['sha256']=sha(held);self.save()
        with self.assertRaisesRegex(ValueError,'Reserved OOT'):load_dataset(self.path)
    def test_policy_selects_per_date(self):
        f=pd.DataFrame({'label':[1,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0],'data_as_of_ts':['one']*10+['two']*10,'training_observation_id':[str(i) for i in range(20)]})
        p=np.array([.9]+[.8]*9+[.1]+[.01]*9)
        m=evaluate('test','ALL',f,p);self.assertEqual(m['tp'],2);self.assertEqual(m['recall'],1);self.assertEqual(m['fp'],0)

if __name__=='__main__':unittest.main()
