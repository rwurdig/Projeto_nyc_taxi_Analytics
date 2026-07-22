SELECT
  pickup_hour,
  COUNT(*) AS credit_card_trip_count,
  ROUND(SAFE_DIVIDE(COUNTIF(tip_amount > 0), COUNT(*)) * 100, 1)
    AS positive_tip_trip_share_pct,
  ROUND(AVG(tip_amount), 2) AS average_recorded_tip_amount,
  ROUND(
    SAFE_DIVIDE(
      CAST(SUM(tip_amount) AS FLOAT64),
      CAST(SUM(total_amount - tip_amount) AS FLOAT64)
    ) * 100,
    2
  ) AS recorded_tip_rate_pct
FROM `__PROJECT_ID__.taxi_silver.trips`
WHERE source_month = @source_month
  AND is_analytics_eligible
  AND payment_type = 1
GROUP BY pickup_hour
ORDER BY pickup_hour;
