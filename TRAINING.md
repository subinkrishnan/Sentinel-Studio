# COM01 Training module

This detachable experimental module adds `training.html` to Studio. Existing Prepaid data and rendering code are unchanged. Remove the Training navigation link to hide the entry point; this does not provide access control. The local API requires a token. GitHub Pages is a public static interface, not a private training service.

## Local setup

Use Python 3.11 or later on your own machine:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r training_backend/requirements.txt
export COM01_RUNNER_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python training_backend/server.py --config /absolute/path/dataset.json --artifacts /absolute/path/com01-artifacts
```

Open http://127.0.0.1:8765/training.html on the same computer. Enter the token you generated into the console, then connect. Keep the token outside GitHub. It remains in browser memory only. HTTPS GitHub Pages to localhost may require browser local-network permission; the local page is the dependable route. The service binds only to loopback.

Prepare a dataset configuration using `dataset.example.json`. It must reference corrected historical development CSVs and a custodian-provided reserved-service exclusion list, with their actual checksums. Do not use the primary OOT or current blind 10K as development inputs. Original E7 data has identified availability/parity defects; setting a flag does not fix these. `feature_corrections_verified` is an operator attestation and evidence reference, not an independent verification of raw event timestamps.

## What works

- Detachable Training menu/page, dataset inventory and development checklist.
- Authenticated local API, one development job at a time, persistent run records and interrupted-job recovery.
- SHA checks, binary-label checks, observation uniqueness, chronological maturity, reserved-service exclusions and numeric feature coverage.
- Purged final-date calibration, LR baseline, available XGB/CatBoost/LightGBM candidates, per-date top-10% metrics, calibration/Brier and no-churn baseline.
- Model, metrics and manifest downloads. Artifacts stay on the local machine. Uploaded external models are not deserialised.

## Remaining gates

- [ ] Correct and independently verify the raw-source historical builder and SQL parity; regenerate development assets.
- [ ] Define development qualification and acceptance criteria before final evaluation.
- [ ] Add time-aware CV/tuning and explainability evidence. Current runner is a fixed-parameter development comparison, not the complete approved tournament.
- [ ] Reconcile E7 with deployed newchurn10 and explain the 6,666 population.
- [ ] Verify supported Sentinel APIs before implementing model import/export/registration.
- [ ] Implement separate candidate freeze and one-time OOT acceptance workflow.
- [ ] Package and approve immutable Gold pipeline and governed COM01 mart.
- [ ] Score protected blind population only after acceptance; freeze before truth release.
- [ ] Connect Postpaid Executive Brief to latest published PASS run and reconcile totals.

No OOT, blind, model upload, engine publication or Studio metric mutation is implemented. No candidate is automatically qualified. The console intentionally keeps those stages pending rather than simulating success. Experimental console is separate from customer-facing Prepaid. Backend packaging can move to Shyam's engine later without rewriting the console API.
