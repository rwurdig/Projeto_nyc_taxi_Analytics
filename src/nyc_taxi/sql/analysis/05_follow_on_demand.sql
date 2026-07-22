WITH dropoffs AS (
  SELECT
    dropoff_location_id AS dropoff_zone_id,
    DATETIME_TRUNC(dropoff_datetime, HOUR) AS dropoff_window,
    COUNT(*) AS destination_trips
  FROM `__PROJECT_ID__.taxi_silver.trips`
  WHERE source_month = @source_month
    AND is_analytics_eligible
    AND dropoff_location_id NOT IN (264, 265)
  GROUP BY dropoff_zone_id, dropoff_window
),
pickups AS (
  SELECT
    pickup_location_id AS pickup_zone_id,
    DATETIME(service_date, TIME(pickup_hour, 0, 0)) AS pickup_window,
    SUM(trip_count) AS next_hour_pickups
  FROM `__PROJECT_ID__.taxi_gold.zone_hour_metrics`
  WHERE source_month = @source_month
  GROUP BY pickup_zone_id, pickup_window
),
destinations AS (
  SELECT
    dropoffs.dropoff_zone_id,
    zones.borough,
    zones.zone_name,
    SUM(dropoffs.destination_trips) AS destination_trips,
    SUM(COALESCE(pickups.next_hour_pickups, 0)) AS next_hour_pickups
  FROM dropoffs
  JOIN `__PROJECT_ID__.taxi_silver.taxi_zones` AS zones
    ON dropoffs.dropoff_zone_id = zones.location_id
  LEFT JOIN pickups
    ON dropoffs.dropoff_zone_id = pickups.pickup_zone_id
    AND DATETIME_ADD(dropoffs.dropoff_window, INTERVAL 1 HOUR)
      = pickups.pickup_window
  GROUP BY dropoff_zone_id, borough, zone_name
  HAVING SUM(dropoffs.destination_trips) >= 200
),
scored AS (
  SELECT
    destinations.*,
    ROUND(SAFE_DIVIDE(next_hour_pickups, destination_trips), 4)
      AS pickups_per_dropoff
  FROM destinations
)
SELECT
  ROW_NUMBER() OVER (
    ORDER BY pickups_per_dropoff DESC, destination_trips DESC, dropoff_zone_id
  ) AS rank,
  dropoff_zone_id,
  borough,
  zone_name,
  destination_trips,
  next_hour_pickups,
  pickups_per_dropoff
FROM scored
ORDER BY rank
LIMIT 20;
