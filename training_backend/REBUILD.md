# Historical development replay

`rebuild_development.py` creates a candidate historical asset from the exact
v0.2.2 SAFE source and original v0.1 development CSVs. It does not fit models,
open the primary OOT CSV, load blind data, publish to Sentinel or edit Confluence.

The source ZIP, reference ZIP and train/validation member hashes are checked.
Labels, observation IDs, ordering within each split and membership are retained.
This is feature reconciliation, not independent label approval.

For each development date, creation and ingestion timestamps must be present and
no later than the cutoff. Contract records updated after the cutoff are excluded.
Event windows are open on the left and closed on the right. Balance ties use the
source ID and negative balances are preserved; contract remaining days use floor
without zero-clipping, consistent with the E7 production SELECT. Non-MB data
usage fails rather than silently diverging from the SQL units.

The exclusion list conservatively contains every source service outside verified
development membership, including reserved and ineligible services. Its count
must not be reported as the exact primary OOT population.

Example on Subin's Mac (activate no shell environment):

```bash
.venv/bin/python training_backend/rebuild_development.py \
  --source "$HOME/Downloads/COM01_Historical_STDF_SOURCE_10K_v0.2.2_SAFE_FOR_VINIT.zip" \
  --reference "$HOME/Downloads/model ch/com01_pit_training_dataset_v0_1.zip" \
  --output "$HOME/Documents/Sentinel-COM01/rebuild-v0.2"
```

The output directory must be new or empty. Existing evidence and downloaded
source/reference packages are never overwritten. Inspect `rebuild_report.json`
for changes and coverage failures. `dataset.json` deliberately leaves
`feature_corrections_verified` false; do not flip it to bypass unresolved gaps.

Remaining requirements: PostgreSQL runtime feature and population parity,
historical mutable-record versions, source completeness and independent label
review. In the verified source all 5,000 contract rows have updates after the last
validation cutoff. Under the production SELECT's guard this cannot provide a
historically usable contract feature. Restoring earlier contract versions or
agreeing and freezing a revised feature contract is required before qualification.
No timestamp is rewritten to manufacture availability.

Tests:

```bash
.venv/bin/python -m unittest discover -s training_backend -p 'test_*.py'
```
