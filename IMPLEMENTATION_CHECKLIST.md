# COM01 Training implementation status — 3 October 2026

| Task | Status | Evidence or dependency |
|---|---|---|
| Inspect existing Studio | Done | Public static HTML/CSS/JS project; Prepaid rendering unchanged |
| Detachable Training menu and standalone page | Implemented locally | Separate training.html; attach_menu.py can add/remove menu |
| Dataset inventory and checks | Implemented | Source/train/validation checksums, label checks, coverage, reserved-service exclusions |
| Historical availability correction and feature parity | Pending | Original source builder defects still require correction; training blocked until evidence supplied |
| Local training jobs and persistent logs | Implemented | Loopback Python service with token; one concurrent development run |
| LR and challenger comparisons | Initial implementation | Fixed parameters; optional installed challengers; purged calibration; CV/tuning pending |
| Accuracy, baseline, precision/recall, lift, PR-AUC and Brier | Implemented | Per-date budget; aggregate plus period metrics |
| Artifact downloads | Implemented | Local models, metric CSV and manifest with SHA256 |
| External model import and Sentinel uploads | Pending | Supported APIs and safe artifact handling need verification |
| Reconcile E7/newchurn10 | Pending | Serving wrapper identity and 6,666 population |
| Model qualification, OOT acceptance | Pending / blocked | Acceptance criteria and separate controlled workflow |
| Blind scoring, Gold publication and Postpaid Studio data | Pending / blocked | Accepted model and engine integration |
| Automated checks | Passed | Six guardrail/metric tests; LR train→evaluate→artifact fixture test; JS syntax |
| Browser visual verification | Pending | Not yet previewed in browser |
| GitHub branch and deployment | Branch upload in progress | Repository installation restored; com01-training-console branch created; deployment pending review |

This is an initial functional development module, not a completed COM01 recovery. Test-fixture metrics are not COM01 metrics and are not bundled as production evidence. No OOT or blind data was evaluated. No Confluence, engine or live Studio changes were made.
