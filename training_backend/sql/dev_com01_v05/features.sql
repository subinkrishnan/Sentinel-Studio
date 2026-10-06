-- DEV EXPERIMENT ONLY. Read-only feature projection from isolated Bronze sources.
-- Coverage control must be independently verified and provisioned first.
-- Do not use NOW(): historical benchmark predictions need matching cutoffs.
-- LOCAL SYNTHETIC CANDIDATE. New overdue and renewed-contract semantics; not engine-approved.
-- PostgreSQL 14+ read-only feature SELECT generated from the supplied tmform_* DDL.
-- Bind :as_of to a timezone-qualified cutoff; do not concatenate user input.
-- Execute in a UTC, read-only, repeatable-read transaction.
-- No feature view is required. The com01_source_coverage ETL control must exist
-- and attest completeness for all required sources; see coverage_control.sql.
-- DDL types are TEXT, so casts are explicit. Versioned source history is required.
WITH
p AS (
    SELECT CAST(:as_of AS TIMESTAMPTZ) AS t0
),
required_sources(name) AS (VALUES
    ('tmform_a_service_instance'), ('tmform_a_service_status_history'),
    ('tmform_a_contract_detail'), ('tmform_d_usage_event'),
    ('tmform_e_invoice'), ('tmform_e_invoice_balance_history'),
    ('tmform_e_payment_transaction'), ('tmform_f_complaint'),
    ('tmform_f_customer_interaction'), ('tmform_j_product_order'),
    ('tmform_k_service_impact_event'), ('tmform_m_digital_session'),
    ('tmform_a_customer_account')
),
coverage AS (
    SELECT MIN(c.history_start) AS history_start
    FROM required_sources r CROSS JOIN p
    LEFT JOIN public.silver__com01v05_0fb5f846_source_coverage c ON c.source_table = r.name AND c.population_scope = 'COM01'
    HAVING COUNT(c.source_table) = 13
       AND COUNT(DISTINCT c.source_table) = 13
       AND BOOL_AND(c.complete_through >= p.t0)
       AND BOOL_AND(c.history_start <= p.t0 - INTERVAL '90 days')
),
status_ranked AS (
    SELECT h.*, ROW_NUMBER() OVER (
        PARTITION BY h.service_instance_id
        ORDER BY NULLIF(h.status_start_ts,'')::timestamptz DESC,
                 NULLIF(h.status_sequence_no,'')::numeric DESC NULLS LAST,
                 h.service_status_history_id DESC) AS rn
    FROM public.bronze__com01v05_0fb5f846_tmform_a_service_status_history h CROSS JOIN p
    WHERE NULLIF(h.status_start_ts,'')::timestamptz <= p.t0
      AND NULLIF(h.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(h.ingested_ts,'')::timestamptz <= p.t0
),
population AS (
    SELECT s.service_instance_id, s.customer_id, p.t0,
           NULLIF(s.activation_date,'')::timestamptz AS activated_at
    FROM public.bronze__com01v05_0fb5f846_tmform_a_service_instance s CROSS JOIN p CROSS JOIN coverage c
    JOIN status_ranked h ON h.service_instance_id = s.service_instance_id AND h.rn = 1
    WHERE UPPER(h.service_status) = 'ACTIVE'
      AND UPPER(s.billing_model) = 'POSTPAID'
      AND UPPER(s.service_type) = 'MOBILE'
      AND NULLIF(s.activation_date,'')::timestamptz <= p.t0 - INTERVAL '90 days'
      AND NULLIF(s.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(s.ingested_ts,'')::timestamptz <= p.t0
      -- End-state master service_status is deliberately not used.
      -- EXISTS validates the customer link without causing a fan-out join.
      AND EXISTS (SELECT 1 FROM public.bronze__com01v05_0fb5f846_tmform_a_customer_account a
                  WHERE a.customer_id = s.customer_id
                    AND NULLIF(a.created_ts,'')::timestamptz <= p.t0
                    AND NULLIF(a.ingested_ts,'')::timestamptz <= p.t0)
),
usage_agg AS (
    SELECT u.service_instance_id,
        COALESCE(SUM(NULLIF(u.usage_quantity,'')::numeric) FILTER (
            WHERE UPPER(u.usage_type) IN ('DATA','ROAMING_DATA')
              AND NULLIF(u.event_ts,'')::timestamptz > p.t0 - INTERVAL '30 days'),0) AS current_mb,
        COALESCE(SUM(NULLIF(u.usage_quantity,'')::numeric) FILTER (
            WHERE UPPER(u.usage_type) IN ('DATA','ROAMING_DATA')
              AND NULLIF(u.event_ts,'')::timestamptz <= p.t0 - INTERVAL '30 days'),0) AS previous_mb,
        COUNT(DISTINCT (NULLIF(u.event_ts,'')::timestamptz AT TIME ZONE 'UTC')::date) FILTER (
            WHERE NULLIF(u.event_ts,'')::timestamptz > p.t0 - INTERVAL '30 days') AS active_days
    FROM public.bronze__com01v05_0fb5f846_tmform_d_usage_event u CROSS JOIN p
    WHERE NULLIF(u.event_ts,'')::timestamptz > p.t0 - INTERVAL '60 days'
      AND NULLIF(u.event_ts,'')::timestamptz <= p.t0
      AND NULLIF(u.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(u.ingested_ts,'')::timestamptz <= p.t0
    GROUP BY u.service_instance_id
),
invoice_agg AS (
    SELECT i.customer_id, AVG(NULLIF(i.invoice_amount,'')::numeric) AS arpu_sgd
    FROM public.bronze__com01v05_0fb5f846_tmform_e_invoice i CROSS JOIN p
    WHERE NULLIF(i.invoice_date,'')::timestamptz > p.t0 - INTERVAL '90 days'
      AND NULLIF(i.invoice_date,'')::timestamptz <= p.t0
      AND NULLIF(i.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(i.ingested_ts,'')::timestamptz <= p.t0
    GROUP BY i.customer_id
),
balances_ranked AS (
    SELECT b.*, ROW_NUMBER() OVER (
        PARTITION BY b.invoice_id
        ORDER BY NULLIF(b.transaction_ts,'')::timestamptz DESC, b.balance_history_id DESC) AS rn
    FROM public.bronze__com01v05_0fb5f846_tmform_e_invoice_balance_history b CROSS JOIN p
    WHERE NULLIF(b.invoice_id,'') IS NOT NULL
      AND NULLIF(b.transaction_ts,'')::timestamptz <= p.t0
      AND NULLIF(b.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(b.ingested_ts,'')::timestamptz <= p.t0
),
balances AS (
    SELECT i.customer_id,
        SUM(CASE WHEN NULLIF(i.due_date,'')::date::timestamptz + INTERVAL '1 day' <= p.t0
                 THEN GREATEST(NULLIF(b.outstanding_amount,'')::numeric,0)
                 ELSE 0 END) AS outstanding
    FROM public.bronze__com01v05_0fb5f846_tmform_e_invoice i CROSS JOIN p
    JOIN balances_ranked b ON b.invoice_id=i.invoice_id AND b.customer_id=i.customer_id AND b.rn=1
    WHERE NULLIF(i.invoice_date,'')::timestamptz <= p.t0
      AND NULLIF(i.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(i.ingested_ts,'')::timestamptz <= p.t0
    GROUP BY i.customer_id
),
payments AS (
    SELECT x.customer_id, COUNT(*) AS failed_count
    FROM public.bronze__com01v05_0fb5f846_tmform_e_payment_transaction x CROSS JOIN p
    WHERE NULLIF(x.transaction_ts,'')::timestamptz > p.t0 - INTERVAL '90 days'
      AND NULLIF(x.transaction_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.ingested_ts,'')::timestamptz <= p.t0
      AND UPPER(x.payment_status) IN ('FAILED','OVERDUE','DECLINED','REJECTED','RETURNED')
    GROUP BY x.customer_id
),
complaints AS (
    SELECT x.customer_id, COUNT(*) AS complaint_count
    FROM public.bronze__com01v05_0fb5f846_tmform_f_complaint x CROSS JOIN p
    WHERE NULLIF(x.submitted_ts,'')::timestamptz > p.t0 - INTERVAL '30 days'
      AND NULLIF(x.submitted_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.ingested_ts,'')::timestamptz <= p.t0
    GROUP BY x.customer_id
),
contacts AS (
    SELECT x.customer_id, GREATEST(COUNT(*) - 1,0) AS repeat_count
    FROM public.bronze__com01v05_0fb5f846_tmform_f_customer_interaction x CROSS JOIN p
    WHERE NULLIF(x.started_ts,'')::timestamptz > p.t0 - INTERVAL '30 days'
      AND NULLIF(x.started_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.ingested_ts,'')::timestamptz <= p.t0
    GROUP BY x.customer_id
),
impacts AS (
    SELECT x.service_instance_id, COUNT(*) AS incident_count,
        SUM(GREATEST(0,EXTRACT(EPOCH FROM (
            LEAST(COALESCE(NULLIF(x.resolved_ts,'')::timestamptz,p.t0),p.t0)
            - NULLIF(x.detected_ts,'')::timestamptz)) / 60)) AS degraded_minutes
    FROM public.bronze__com01v05_0fb5f846_tmform_k_service_impact_event x CROSS JOIN p
    WHERE NULLIF(x.detected_ts,'')::timestamptz > p.t0 - INTERVAL '30 days'
      AND NULLIF(x.detected_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.ingested_ts,'')::timestamptz <= p.t0
    GROUP BY x.service_instance_id
),
digital AS (
    SELECT x.customer_id,
        COUNT(DISTINCT (NULLIF(x.started_ts,'')::timestamptz AT TIME ZONE 'UTC')::date) AS active_days
    FROM public.bronze__com01v05_0fb5f846_tmform_m_digital_session x CROSS JOIN p
    WHERE NULLIF(x.started_ts,'')::timestamptz > p.t0 - INTERVAL '30 days'
      AND NULLIF(x.started_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.ingested_ts,'')::timestamptz <= p.t0
    GROUP BY x.customer_id
),
orders AS (
    SELECT x.service_instance_id, COUNT(*) AS change_count
    FROM public.bronze__com01v05_0fb5f846_tmform_j_product_order x CROSS JOIN p
    WHERE NULLIF(x.submitted_ts,'')::timestamptz > p.t0 - INTERVAL '90 days'
      AND NULLIF(x.submitted_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.ingested_ts,'')::timestamptz <= p.t0
      AND UPPER(x.order_type) IN ('PLAN_CHANGE','ADD_ON_CHANGE')
    GROUP BY x.service_instance_id
),
contracts_ranked AS (
    SELECT x.*, ROW_NUMBER() OVER (PARTITION BY x.service_instance_id
        ORDER BY NULLIF(x.created_ts,'')::timestamptz DESC, x.contract_id DESC) AS rn
    FROM public.bronze__com01v05_0fb5f846_tmform_a_contract_detail x CROSS JOIN p
    WHERE NULLIF(x.contract_start_date,'')::timestamptz <= p.t0
      AND NULLIF(x.created_ts,'')::timestamptz <= p.t0
      AND NULLIF(x.ingested_ts,'')::timestamptz <= p.t0
      AND (NULLIF(x.updated_ts,'') IS NULL OR NULLIF(x.updated_ts,'')::timestamptz <= p.t0)
)
SELECT 'COM01HIST-' || s.service_instance_id || '-' || TO_CHAR(s.t0 AT TIME ZONE 'UTC','YYYYMMDD') AS training_observation_id,
    s.customer_id, s.service_instance_id, s.t0 AS data_as_of_ts,
    30 AS prediction_horizon_days,
    'COM01_MOBILE_POSTPAID_VOLUNTARY_30D'::text AS churn_definition_id,
    '1.0-DRAFT'::text AS churn_definition_version,
    'COM01_CHURN_FEATURE_SET'::text AS feature_set_id,
    '0.5.0-SOURCE-FIRST-BENCHMARK'::text AS feature_set_version,
    90 AS available_history_days, -- guaranteed lower bound from coverage and tenure gates
    'SUFFICIENT'::text AS feature_coverage_status, 1.0 AS domain_availability_score,
    FLOOR(EXTRACT(EPOCH FROM(s.t0-s.activated_at))/86400) AS service_tenure_days,
    i.arpu_sgd,
    COALESCE(u.current_mb,0) AS usage_data_mb_sum_30d,
    COALESCE(u.previous_mb,0) AS usage_data_mb_sum_prev30d,
    COALESCE(u.current_mb,0)-COALESCE(u.previous_mb,0) AS usage_data_mb_delta_30d_vs_prev30d,
    COALESCE(u.active_days,0) AS usage_active_days_count_30d,
    b.outstanding AS billing_overdue_amount_sgd,
    COALESCE(pay.failed_count,0) AS billing_payment_failure_count_90d,
    COALESCE(c.complaint_count,0) AS care_complaint_count_30d,
    COALESCE(ct.repeat_count,0) AS care_repeat_contact_count_30d,
    COALESCE(n.incident_count,0) AS network_incident_count_30d,
    COALESCE(n.degraded_minutes,0) AS network_degraded_minutes_30d,
    COALESCE(d.active_days,0) AS digital_active_days_count_30d,
    COALESCE(o.change_count,0) AS product_change_count_90d,
    CASE WHEN k.contract_id IS NULL THEN NULL
         WHEN UPPER(k.contract_status)='CANCELLED' OR NULLIF(k.commitment_months,'')::numeric=0 THEN 0
         ELSE GREATEST(FLOOR(EXTRACT(EPOCH FROM(NULLIF(k.contract_end_date,'')::timestamptz-s.t0))/86400),0) END AS contract_remaining_days
FROM population s
LEFT JOIN usage_agg u ON u.service_instance_id=s.service_instance_id
LEFT JOIN invoice_agg i ON i.customer_id=s.customer_id
LEFT JOIN balances b ON b.customer_id=s.customer_id
LEFT JOIN payments pay ON pay.customer_id=s.customer_id
LEFT JOIN complaints c ON c.customer_id=s.customer_id
LEFT JOIN contacts ct ON ct.customer_id=s.customer_id
LEFT JOIN impacts n ON n.service_instance_id=s.service_instance_id
LEFT JOIN digital d ON d.customer_id=s.customer_id
LEFT JOIN orders o ON o.service_instance_id=s.service_instance_id
LEFT JOIN contracts_ranked k ON k.service_instance_id=s.service_instance_id AND k.rn=1;
