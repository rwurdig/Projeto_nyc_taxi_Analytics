WITH classified AS (
  SELECT
    CASE pickup_location_id
      WHEN 1 THEN 'EWR'
      WHEN 132 THEN 'JFK'
      WHEN 138 THEN 'LGA'
      ELSE 'non-airport'
    END AS pickup_group,
    CASE pickup_location_id WHEN 1 THEN 1 WHEN 132 THEN 2 WHEN 138 THEN 3 ELSE 4 END
      AS group_order,
    trip_distance,
    trip_duration_minutes,
    total_amount
  FROM `__PROJECT_ID__.taxi_silver.trips`
  WHERE source_month = @source_month
    AND is_analytics_eligible
    AND pickup_location_id NOT IN (264, 265)
)
SELECT
  pickup_group,
  COUNT(*) AS trip_count,
  ROUND(AVG(trip_distance), 2) AS average_distance_miles,
  ROUND(AVG(trip_duration_minutes), 2) AS average_duration_minutes,
  ROUND(
    SAFE_DIVIDE(CAST(SUM(total_amount) AS FLOAT64) * 60,
      SUM(trip_duration_minutes)), 2
  ) AS gross_receipts_per_engaged_hour
FROM classified
GROUP BY pickup_group, group_order
ORDER BY group_order;
