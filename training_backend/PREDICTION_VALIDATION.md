# Dev prediction comparison in Studio

The Sentinel integration tab now accepts an operator-imported Dev scoring CSV and compares it against the selected run's hashed local validation predictions. It does not invoke Live Test, fetch Dev scores, create features, approve/promote models, or publish Gold/Mart.

## Readiness

Complete source upload and content checks, verify Silver feature parity, and stage the selected completed run/model using the reviewed Dev SQL. A fresh staging upload records the run/model, engine model name/version, serving artifact hash and feature SQL hash. This identity is required before comparison. Earlier uploads without this record are not inferred from current config.

## Export contract

Export the full local validation population, across its validation dates, from the corresponding Dev scoring execution. Normalise the platform result into UTF-8 CSV with these exact columns:

`training_observation_id,service_instance_id,data_as_of_ts,probability,threshold,predicted_label,model_name,model_version`

- `probability` is the calibrated positive-class probability, not a risk band, percentage, hard label or uncalibrated model score. Retain full precision.
- `threshold` is the frozen calibration threshold for the selected model, not a threshold selected on Dev validation labels.
- `predicted_label` is 0 or 1, using probability >= threshold. If the Dev scoring interface returns only probabilities, derive this column explicitly under the frozen policy; this then validates that policy applied to Dev probabilities, not an independent engine decision output.
- Model name/version must identify the actual Dev scoring execution. Adding expected values to an unrelated file is not valid evidence.
- Observation and service identifiers must identify the same historical cutoff as the local reference. Timestamps require a timezone and are normalised to UTC. Order need not match.
- Dev labels are not trusted as ground truth; metrics use labels in the immutable local reference.
- Supply every validation observation exactly once. Export additional scoring populations separately. Truncated 1,000-row query previews fail the missing-observation check.

In Studio, select the staged run/model above, choose this CSV and click **Compare Dev predictions**. Refreshes show the latest comparison per run/model. Each attempt preserves the uploaded CSV and a hashed JSON report as downloadable run artifacts, including failed comparisons. Studio accepts files up to 12 MiB; backend requests are bounded at 16 MiB and 200,000 rows.

## Checks and meaning

The report checks missing/extra/duplicate observations, model identity, calibrated probability differences (absolute tolerance 1e-7), frozen threshold equality (1e-12), exact classification agreement and internal consistency of Dev decisions. Even a probability difference below tolerance fails if it crosses the classification threshold. Nonfinite/out-of-range numbers, malformed CSV or timezone-free timestamps block comparison.

`PREDICTION_PARITY_PASS` means the supplied scoring export matches the immutable local reference under these checks. It does not prove how that file was obtained: reports explicitly retain `OPERATOR_IMPORTED_DEV_SCORING_CSV` and `live_sdk_fetch_verified: false`. Feature parity, independent model qualification, OOT evidence, engine approval and publication remain separate gates. Classification accuracy, precision, recall, confusion counts and Brier are reported on matched rows only; missing or extra observations still fail overall parity.

The comparator is ready while the source upload runs. Actual Dev evidence remains pending until feature/scoring execution is available. Do not copy local prediction CSVs into the import as evidence of Dev execution.
