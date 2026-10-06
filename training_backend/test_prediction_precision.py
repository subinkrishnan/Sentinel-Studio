import io,unittest
import numpy as np,pandas as pd
from verify_results_v05 import check_csv_probabilities
class PrecisionChecks(unittest.TestCase):
 def test_float32_shortest_csv_recovers_exact_values(self):
  p=np.array([.123456789,.987654321],dtype=np.float32);text=pd.DataFrame({'probability':p}).to_csv(index=False);q=pd.read_csv(io.StringIO(text),float_precision='round_trip').probability.to_numpy()
  self.assertFalse(np.allclose(p,q,rtol=1e-12,atol=1e-12));self.assertEqual(check_csv_probabilities(p,q,'XGB')['csv_native_precision_check'],'PASS')
 def test_single_float32_ulp_change_fails(self):
  p=np.array([.3],dtype=np.float32);q=np.nextafter(p,np.float32(1)).astype(np.float64)
  with self.assertRaisesRegex(ValueError,'native precision'):check_csv_probabilities(p,q,'XGB')
 def test_float64_gate_not_relaxed(self):
  p=np.array([.123456789],dtype=np.float64)
  with self.assertRaisesRegex(ValueError,'native precision'):check_csv_probabilities(p,p+1e-8,'LR')
 def test_invalid_values_fail(self):
  for q in [[np.nan],[1.1],[-.1]]:
   with self.assertRaises(ValueError):check_csv_probabilities(np.array([.1]),q,'LR')
 def test_expanded_float32_export_retains_full_value(self):
  p=np.array([.123456789],dtype=np.float32);text=pd.DataFrame({'probability':p.astype(np.float64)}).to_csv(index=False);q=pd.read_csv(io.StringIO(text),float_precision='round_trip').probability.to_numpy();np.testing.assert_array_equal(p.astype(np.float64),q)
if __name__=='__main__':unittest.main()
