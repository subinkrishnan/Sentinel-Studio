-- Read-only. Counts alone do not attest content or historical completeness.
SELECT 'tmform_a_contract_detail' AS source_name, COUNT(*) AS actual_rows, 19417 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_a_contract_detail
UNION ALL
SELECT 'tmform_a_customer_account' AS source_name, COUNT(*) AS actual_rows, 8000 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_a_customer_account
UNION ALL
SELECT 'tmform_a_service_instance' AS source_name, COUNT(*) AS actual_rows, 8000 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_a_service_instance
UNION ALL
SELECT 'tmform_a_service_status_history' AS source_name, COUNT(*) AS actual_rows, 11094 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_a_service_status_history
UNION ALL
SELECT 'tmform_d_usage_event' AS source_name, COUNT(*) AS actual_rows, 790913 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_d_usage_event
UNION ALL
SELECT 'tmform_e_invoice' AS source_name, COUNT(*) AS actual_rows, 95730 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_e_invoice
UNION ALL
SELECT 'tmform_e_invoice_balance_history' AS source_name, COUNT(*) AS actual_rows, 191460 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_e_invoice_balance_history
UNION ALL
SELECT 'tmform_e_payment_transaction' AS source_name, COUNT(*) AS actual_rows, 101571 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_e_payment_transaction
UNION ALL
SELECT 'tmform_f_complaint' AS source_name, COUNT(*) AS actual_rows, 22500 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_f_complaint
UNION ALL
SELECT 'tmform_f_customer_interaction' AS source_name, COUNT(*) AS actual_rows, 54619 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_f_customer_interaction
UNION ALL
SELECT 'tmform_j_product_order' AS source_name, COUNT(*) AS actual_rows, 8060 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_j_product_order
UNION ALL
SELECT 'tmform_k_service_impact_event' AS source_name, COUNT(*) AS actual_rows, 21696 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_k_service_impact_event
UNION ALL
SELECT 'tmform_m_digital_session' AS source_name, COUNT(*) AS actual_rows, 474621 AS expected_rows, MIN(NULLIF(ingested_ts,'')::timestamptz) AS earliest_source_ingested_ts, MAX(NULLIF(ingested_ts,'')::timestamptz) AS latest_source_ingested_ts FROM public.bronze__com01v05_0fb5f846_tmform_m_digital_session;
