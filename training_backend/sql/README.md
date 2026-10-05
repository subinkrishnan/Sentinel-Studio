# COM01 v0.5 Dev Silver feature preparation

Prepared only. No engine SQL has been executed, no Silver table has been provisioned, and Studio staging configuration is unchanged.

The frozen local PostgreSQL query produces the 15 inputs required by `COM01_LOCAL_SYNTHETIC_15F_V05`. The Dev adaptation reads `public.bronze__com01v05_0fb5f846_*`. Original canonical names stay unchanged. This projection is the feature-building step; it does not by itself create/materialise a Silver feature table.

## Files

- `com01_v05_frozen_features.sql`: byte-identical SQL from COM01_v05_Implemented_Workflow.zip, SHA256 e577ccaebc8c58dfad44d3c78a328690009c7ac0339c0a24af685d30a81a486b.
- `com01_v05_source_manifest.json`: frozen 13-source manifest for the uploaded benchmark.
- `dev_com01_v05/features.sql`: read-only Dev feature SELECT, with `:as_of` binding placeholder.
- `dev_com01_v05/source_checks.sql`: counts and historical source-ingest timestamp checks.
- `dev_com01_v05/contract.json`: exact source mapping, hashes, pending gates and coverage contract.

All source feature expressions and historical filters are preserved. Only physical relation references and a distinct-source coverage safeguard change. No labels, future outcomes or termination dates are model inputs.

## Before live execution

1. Finish the uploader. Verify counts for all 13 tables against the manifest and reconcile the uploader checkpoint. Counts are necessary but not sufficient.
2. Verify uploaded payload content, primary-key uniqueness and historical `created_ts`/`ingested_ts` values against the frozen exports. Ingestion must preserve the supplied historical timestamps; if the engine substituted the upload date, stop and resolve that mapping before any historical scoring. Never remove the timestamp filters to make results appear.
3. Provision the isolated coverage control `public.silver__com01v05_0fb5f846_source_coverage` through the normal Dev maker/checker process. Its columns are `source_table text`, `population_scope text`, `history_start timestamptz`, `complete_through timestamptz`, with one unique row per source/scope. Source names use the canonical logical `tmform_*` names and scope is `COM01`.
4. Populate coverage only after source/content/completeness verification. Do not copy local fixture coverage dates as proof of live ETL completeness. No control records or DDL are included here for automatic execution.
5. Select a historical cutoff from the benchmark inventory, matching the local observation date. Execute in UTC with a consistent read-only snapshot. `:as_of` is a binding placeholder, not SQL to paste unmodified into the Workbench. The preparation helper can produce a safely rendered fixed-cutoff query.
6. Export all Dev feature results and compare against the matching local `postgres_features.jsonl`, keyed by service ID and cutoff. Compare all 15 feature cells with absolute tolerance 1e-6 and relative tolerance 1e-9. A 1,000-row query response is not a full-population check; use the SDK export route for full results.
7. Confirm one observation per service/cutoff, no required feature null/nonfinite values, and no missing local observations. Local SQL included 455 extra rows across benchmark dates due to supervised-label exclusions; use the documented label exclusion rules when comparing to training/validation CSVs, rather than discarding arbitrary extra rows.
8. Only after these gates pass, configure/materialise the reviewed Dev Silver projection, select the completed Studio run, and test staging and calibrated prediction parity. A coverage table name in this SQL is not evidence that a Silver feature dataset has been deployed.

## Prepare a fixed-cutoff query on the Mac

Run `training_backend/prepare_silver_features.py` with `--data-dir` pointing to the current COM01 development package, `--output-dir` pointing to a new folder, and `--as-of` set to an exact timezone-qualified benchmark date. Omit `--as-of` to produce the binding template. Existing output folders are never overwritten. No credentials or Dev API calls are needed.

The original package reports local PostgreSQL parity PASS for 76,367 supervised observations and 1,145,505 feature cells. This is local evidence only. Live Dev content/feature parity, model qualification, Gold/Mart publication and Pulse integration remain pending.
