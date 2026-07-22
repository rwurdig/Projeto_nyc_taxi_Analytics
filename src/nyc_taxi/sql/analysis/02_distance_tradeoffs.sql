WITH banded AS (
  SELECT
    CASE
      WHEN trip_distance < 2 THEN '<2 miles'
      WHEN trip_distance < 5 THEN '2-5 miles'
      WHEN trip_distance < 10 THEN '5-10 miles'
      ELSE '10+ miles'
    END AS distance_band,
    CASE
      WHEN trip_distance < 2 THEN 1
      WHEN trip_distance < 5 THEN 2
      WHEN trip_distance < 10 THEN 3
      ELSE 4
    END AS band_order,
    trip_distance,
    trip_duration_minutes,
    total_amount
  FROM `__PROJECT_ID__.taxi_silver.trips`
  WHERE source_month = @source_month
    AND is_analytics_eligible
),
summary AS (
  SELECT
    distance_band,
    band_order,
    COUNT(*) AS trip_count,
    AVG(trip_distance) AS average_distance_miles,
    AVG(trip_duration_minutes) AS average_duration_minutes,
    SUM(trip_duration_minutes) AS engaged_minutes,
    SUM(total_amount) AS gross_receipts
  FROM banded
  GROUP BY distance_band, band_order
)
SELECT
  distance_band,
  trip_count,
  ROUND(SAFE_DIVIDE(trip_count, SUM(trip_count) OVER ()) * 100, 1)
    AS trip_share_pct,
  ROUND(average_distance_miles, 2) AS average_distance_miles,
  ROUND(average_duration_minutes, 2) AS average_duration_minutes,
  ROUND(SAFE_DIVIDE(CAST(gross_receipts AS FLOAT64) * 60, engaged_minutes), 2)
    AS gross_receipts_per_engaged_hour
FROM summary
ORDER BY band_order;
