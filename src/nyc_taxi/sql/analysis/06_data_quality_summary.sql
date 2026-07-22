WITH counts AS (
  SELECT
    COUNT(*) AS source_rows,
    COUNTIF(is_analytics_eligible) AS eligible_rows,
    COUNTIF(NOT is_analytics_eligible) AS flagged_rows,
    COUNTIF('pickup_outside_source_month' IN UNNEST(quality_issues)) AS outside_rows,
    COUNTIF('invalid_timestamps' IN UNNEST(quality_issues)) AS timestamp_rows,
    COUNTIF('duration_out_of_range' IN UNNEST(quality_issues)) AS duration_rows,
    COUNTIF('distance_out_of_range' IN UNNEST(quality_issues)) AS distance_rows,
    COUNTIF('non_positive_total' IN UNNEST(quality_issues)) AS total_rows,
    COUNTIF('missing_zone_match' IN UNNEST(quality_issues)) AS zone_rows,
    COUNTIF('excluded_payment_type' IN UNNEST(quality_issues)) AS payment_rows,
    COUNTIF('duplicate' IN UNNEST(quality_issues)) AS duplicate_rows
  FROM `__PROJECT_ID__.taxi_silver.trips`
  WHERE source_month = @source_month
),
metrics AS (
  SELECT metric_order, metric, record_count, source_rows
  FROM counts
  CROSS JOIN UNNEST([
    STRUCT(1 AS metric_order, 'source_rows' AS metric, source_rows AS record_count),
    STRUCT(2, 'analytics_eligible', eligible_rows),
    STRUCT(3, 'flagged_rows', flagged_rows),
    STRUCT(4, 'pickup_outside_source_month', outside_rows),
    STRUCT(5, 'invalid_timestamps', timestamp_rows),
    STRUCT(6, 'duration_out_of_range', duration_rows),
    STRUCT(7, 'distance_out_of_range', distance_rows),
    STRUCT(8, 'non_positive_total', total_rows),
    STRUCT(9, 'missing_zone_match', zone_rows),
    STRUCT(10, 'excluded_payment_type', payment_rows),
    STRUCT(11, 'duplicate', duplicate_rows)
  ])
)
SELECT
  metric,
  record_count,
  ROUND(SAFE_DIVIDE(record_count, source_rows) * 100, 3) AS percent_of_rows
FROM metrics
ORDER BY metric_order;
