# Private postpaid COM01 admin

Run this module on the training host. Studio and COM01 Training are served together by the authenticated service. GitHub Pages can preview the interface; it cannot execute Python or securely host private training results. The admin service binds to loopback and protects the page, API, evidence and downloads using an expiring HttpOnly session. No prepaid files are changed.

## Start on your Mac

1. Download this branch into a separate folder; keep the existing Studio folder intact.
2. Use the existing COM01 v0.5 workflow's COMPLETE development directory. The final 2,000-service evidence is evaluation only and must not be configured as training input.
3. Copy `training_backend/admin.example.json` to a local file outside the repository and replace `data_dir` with the absolute COMPLETE development directory. Optional `final_evaluation` is `{ "path": "/absolute/path/final_evaluation_corrected.json", "sha256": "the-file-SHA256" }`.
4. Install requirements in a virtual environment. Run:

```sh
export COM01_RUNNER_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(40))')"
python3 training_backend/admin_server.py --config /absolute/path/local.admin.json --artifacts /absolute/path/private-runs
```

Open Studio and use the generated runner token locally at `http://127.0.0.1:8765/`. Keep the terminal running. Never paste tokens into GitHub or chat. Runner sign-in is separate from Sentinel authentication.

## Sentinel connection

The Dev console's Help → SDK guide documents SDK 0.8.0. Install from its official wheel download; set `SENTINEL_BASE_URL`, `SENTINEL_CLIENT_ID` and `SENTINEL_CLIENT_SECRET` only on the host. Use an existing authorised training credential with gateway.query and model.push. A new API key/service account expands persistent access and must be provisioned deliberately by the owner. This code does not create credentials.

Click **Verify Sentinel connection**. It must return CONNECTED after SDK `SELECT 1 AS ok` succeeds. A browser login does not satisfy this check.

Configure `staging.name` beginning `com01_experiment_`, a new version and the reviewed Silver feature SQL matching the ordered 15-feature contract. The service will not overwrite newchurn10. Complete a development run before staging its calibrated serving export.

The export uses standard sklearn/scipy classes, reproduces probabilities within absolute 1e-7 and verifies identical decisions at the frozen training threshold. Its positive-class probabilities are the serving contract; default classifier `predict()` at 0.5 is not the campaign or frozen-threshold policy. Engine Live Test must verify probability extraction, feature order, schema, dependencies and tolerance before any checker promotes it. The portable object alone does not prove engine compatibility.

Upload lands in STAGING through the SDK. It never promotes, approves, packages, binds, publishes Gold or touches the blind. Live Test, separate checker review, complete Gold feature/model/scoring/mart pipeline and Gold-to-Studio reconciliation remain required.

## Automation and evidence

The runner validates source hashes, source/leakage audit, SQL boundaries/parity, observation identities, mature labels and excluded reserved IDs before fitting. It trains all four candidates, calibrates and freezes thresholds on the earlier development slice, reproduces saved-model predictions and produces portable serving exports. Missing libraries fail the run. Each run has a separate directory, metrics, logs, hashes and downloads. Final acceptance evidence is attached by hash and never reused for training.

Run `python3 -m unittest discover -s training_backend -p 'test_*.py'` for unit checks. Actual engine connectivity, staging upload and Live Test cannot be certified by mocked SDK tests.

Current acceptance is synthetic experiment evidence. No claim of 97% classification accuracy or production qualification is made. Keep private datasets, configs, artifacts and credentials out of the public repository. For multi-user remote hosting, replace the local session mechanism with organisation SSO, TLS, RBAC and a secret store before deployment.


## Integrated Studio

After updating this branch, start `admin_server.py` with your existing config, artifacts directory and port. The root URL opens Studio; its Training menu opens the existing COM01 console on the same origin. Both share the service session, so no second demo login is required. Returning to Executive Brief, Decisions or Reports preserves the session. Signing out ends it for both.

For the current Mac setup using port 8767, open `http://127.0.0.1:8767/`. Update/restart only the Studio service. Leave the independent source uploader terminal running. Do not change its checkpoints or source namespace. Existing artifact directories are reused.

Static hosting cannot run the Python service: the Training preview shows a disconnected state and disables actions. Executive reports and Ask Pulse still use synthetic demo data. This change integrates the training console, not live Mart consumption or model publication. Sentinel credentials remain in the service environment; Dev staging uses the existing verified export and reviewed Silver query checks.

## Mac restart helper

If the running service uses an older token, exit any Python prompt with Ctrl+D, pull this branch and run:

```sh
"$HOME/Downloads/Sentinel-Studio-main/.venv/bin/python" "$HOME/Downloads/Sentinel-COM01-Admin/training_backend/restart_studio.py" --expected-pid YOUR_STUDIO_PID
```

The helper reads the existing local.admin.json, finds run folders in the COM01 local directory, checkout and home/local-artifacts, and refuses ambiguous folders or runs marked RUNNING. Use --artifacts to specify a known existing folder if needed. It verifies the expected listener is Python serving the COM01/Studio token sign-in page before sending SIGTERM only to that PID. It does not stop the source uploader. The new service copies its matching token to the Mac clipboard without printing or storing it. Keep the terminal open, refresh the local Studio URL and paste directly into the token field. Copying another command replaces the clipboard token. Existing Sentinel environment variables are inherited from the launching terminal; credentials configured only in the old process are not recovered by this helper.
