# Configured Studio Mart connection

Authenticated Studio now reads `/api/mart/summary`. It displays the configured Mart's published COM01 risk summary, trend, segments and reasons. It never reads Bronze for executive metrics. The separate static website remains a demonstration.

The connection is prepared but disabled in `admin.example.json`. No Mart relation is assumed to exist, and no schema, source records, config on the Mac, training process or uploader was changed.

## Configure after Mart publication

Add a `mart` object to the Mac's `local.admin.json`, retaining its existing dataset/staging settings:

- `enabled`: set true only after the target Mart exists and its mapping is confirmed.
- `mode`: `dev_experiment` for the current separate namespace, or `canonical` for original table names.
- `table`: one fully qualified `public.mart__...` relation. Dev experiment mode requires the `com01v05_0fb5f846_` namespace. The adapter rejects Bronze/Silver relations and SQL expressions.
- `base_url` and `allowed_hosts`: approved Sentinel HTTPS origin and exact host allowlist. Dev experiment mode is restricted to `dev.sentinel.inalpha.ai`. Production requires its actual approved endpoint, not an inferred URL.
- `business_line`: label for this scoped COM01 Mart, currently Postpaid. The configured relation must already be scoped to the intended use case/business line. This setting labels the data and does not filter a multi-use-case table.
- `columns`: map actual physical fields to `service_id`, `run_id`, `as_of`, `probability`, `risk_band`, `quality_gate`, `publication_status`, `model_version`. These are required. `segment` and `primary_reason` are optional; missing mappings display Unspecified/Unavailable instead of invented classifications or explanations.

`probability` must be calibrated positive-class churn probability in [0,1]. Risk bands must be HIGH/MEDIUM/LOW under the published threshold policy. Flags must identify PASS/PUBLISHED runs. This connection assumes a unique row per service per scoring run, one cutoff and model version per run. An actual Mart at another grain needs an approved view at this contract before configuring it; do not discard duplicates arbitrarily.

## Credentials and production switch

Credentials remain server-side. On Dev, the adapter can reuse `SENTINEL_CLIENT_ID` and `SENTINEL_CLIENT_SECRET`, or use dedicated `SENTINEL_MART_CLIENT_ID` and `SENTINEL_MART_CLIENT_SECRET`. Production requires dedicated Mart credentials and an explicit endpoint/host allowlist; it cannot silently reuse Dev credentials.

Once both environments expose the same logical contract, switching the Mart mode, endpoint, table and physical column mapping requires configuration only and a service restart. No experiment table renaming is required. This does not provision production hosting, network access, credentials or canonical ETL. The training/staging bridge remains Dev-only.

## Run selection and display

A single read-only aggregate query checks whole scoring runs before selecting the latest eligible run. Every row must be PASS/PUBLISHED, with valid identities, finite bounded probabilities, recognised bands, consistent model/cutoff and no duplicate services. It does not filter bad rows out to manufacture a passing run. Older eligible runs can be displayed when a newer attempt fails, with an explicit fallback notice.

Executive Brief shows scored subscribers, high-risk subscribers/share, mean probability, risk bands, up to 12 eligible historical runs, segments and recorded reasons. Reports shows that scoring history. Live campaign decisions, revenue, protected subscriber counts and causal uplift are unavailable through this contract. Ask Pulse uses the separate Assistant bridge and its own readiness checks, documented in PULSE_CONNECTION.md. Mart connectivity alone does not imply Pulse readiness.

NOT_CONFIGURED, NO_PUBLISHED_DATA and BLOCKED states show no synthetic demo fallback. Refresh triggers a read on demand; Bronze uploader and local training are untouched. SDK exception details and credential values are not returned to the browser.

This implementation still needs live testing against the populated experimental Mart. A CONNECTED status means the configured summary query succeeded and returned eligible records; it is not independent proof of model qualification or production readiness.
