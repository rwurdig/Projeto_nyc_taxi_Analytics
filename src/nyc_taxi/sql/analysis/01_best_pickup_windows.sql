WITH grouped AS (
  SELECT
    pickup_location_id AS pickup_zone_id,
    day_type,
    pickup_hour,
    SUM(metrics.trip_count) AS trip_count,
    COUNT(DISTINCT metrics.service_date) AS active_days,
    SUM(metrics.engaged_minutes) AS engaged_minutes,
    SUM(metrics.gross_receipts) AS gross_receipts
  FROM `__PROJECT_ID__.taxi_gold.zone_hour_metrics` AS metrics
  WHERE metrics.source_month = @source_month
    AND metrics.pickup_location_id NOT IN (264, 265)
  GROUP BY pickup_zone_id, day_type, pickup_hour
  HAVING SUM(metrics.trip_count) >= 200
    AND COUNT(DISTINCT metrics.service_date) >= 5
),
scored AS (
  SELECT
    grouped.*,
    zones.borough,
    zones.zone_name,
    ROUND(SAFE_DIVIDE(CAST(gross_receipts AS FLOAT64) * 60, engaged_minutes), 2)
      AS gross_receipts_per_engaged_hour
  FROM grouped
  JOIN `__PROJECT_ID__.taxi_silver.taxi_zones` AS zones
    ON grouped.pickup_zone_id = zones.location_id
)
SELECT
  ROW_NUMBER() OVER (
    ORDER BY gross_receipts_per_engaged_hour DESC, trip_count DESC,
      pickup_zone_id, day_type, pickup_hour
  ) AS rank,
  pickup_zone_id,
  borough,
  zone_name,
  day_type,
  pickup_hour,
  trip_count,
  active_days,
  gross_receipts_per_engaged_hour
FROM scored
ORDER BY rank
LIMIT 20;
