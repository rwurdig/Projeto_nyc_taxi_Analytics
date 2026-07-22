DECLARE active_run_id STRING;

SET active_run_id = (
  SELECT run_id
  FROM `__PROJECT_ID__.taxi_ops.monthly_loads`
  WHERE source_month = @source_month
    AND status = 'RUNNING'
  ORDER BY started_at DESC
  LIMIT 1
);

ASSERT active_run_id IS NOT NULL AS 'No RUNNING monthly load was found';

CREATE TEMP TABLE prepared AS
WITH source_rows AS (
  SELECT
    @source_month AS source_month,
    SAFE_CAST(tpep_pickup_datetime AS DATETIME) AS pickup_datetime,
    SAFE_CAST(tpep_dropoff_datetime AS DATETIME) AS dropoff_datetime,
    SAFE_CAST(PULocationID AS INT64) AS pickup_location_id,
    SAFE_CAST(DOLocationID AS INT64) AS dropoff_location_id,
    SAFE_CAST(trip_distance AS FLOAT64) AS trip_distance,
    SAFE_CAST(payment_type AS INT64) AS payment_type,
    SAFE_CAST(fare_amount AS NUMERIC) AS fare_amount,
    SAFE_CAST(tip_amount AS NUMERIC) AS tip_amount,
    SAFE_CAST(total_amount AS NUMERIC) AS total_amount,
    SAFE_CAST(
      JSON_VALUE(TO_JSON_STRING(source_record), '$.congestion_surcharge')
      AS NUMERIC
    ) AS congestion_surcharge,
    SAFE_CAST(
      COALESCE(
        JSON_VALUE(TO_JSON_STRING(source_record), '$.airport_fee'),
        JSON_VALUE(TO_JSON_STRING(source_record), '$.Airport_fee')
      ) AS NUMERIC
    ) AS airport_fee,
    SAFE_CAST(
      JSON_VALUE(TO_JSON_STRING(source_record), '$.cbd_congestion_fee')
      AS NUMERIC
    ) AS cbd_congestion_fee
  FROM `__STAGING_TABLE__` AS source_record
),
ranked_rows AS (
  SELECT
    source_rows.*,
    ROW_NUMBER() OVER (
      PARTITION BY
        pickup_datetime,
        dropoff_datetime,
        pickup_location_id,
        dropoff_location_id,
        trip_distance,
        payment_type,
        fare_amount,
        tip_amount,
        total_amount
    ) AS duplicate_rank
  FROM source_rows
),
enriched_rows AS (
  SELECT
    ranked_rows.*,
    pickup_zone.borough AS pickup_borough,
    pickup_zone.zone_name AS pickup_zone,
    dropoff_zone.borough AS dropoff_borough,
    dropoff_zone.zone_name AS dropoff_zone,
    DATE(pickup_datetime) AS service_date,
    EXTRACT(HOUR FROM pickup_datetime) AS pickup_hour,
    CASE
      WHEN pickup_datetime IS NULL THEN NULL
      WHEN EXTRACT(DAYOFWEEK FROM pickup_datetime) IN (1, 7) THEN 'weekend'
      ELSE 'weekday'
    END AS day_type,
    DATETIME_DIFF(dropoff_datetime, pickup_datetime, SECOND) / 60.0
      AS trip_duration_minutes
  FROM ranked_rows
  LEFT JOIN `__PROJECT_ID__.taxi_silver.taxi_zones` AS pickup_zone
    ON ranked_rows.pickup_location_id = pickup_zone.location_id
  LEFT JOIN `__PROJECT_ID__.taxi_silver.taxi_zones` AS dropoff_zone
    ON ranked_rows.dropoff_location_id = dropoff_zone.location_id
),
issue_rows AS (
  SELECT
    enriched_rows.*,
    ARRAY_CONCAT(
      IF(
        pickup_datetime IS NOT NULL
          AND DATE_TRUNC(DATE(pickup_datetime), MONTH) != source_month,
        ['pickup_outside_source_month'],
        []
      ),
      IF(
        pickup_datetime IS NULL
          OR dropoff_datetime IS NULL
          OR dropoff_datetime <= pickup_datetime,
        ['invalid_timestamps'],
        []
      ),
      IF(
        trip_duration_minutes IS NULL
          OR trip_duration_minutes < 1
          OR trip_duration_minutes > 240,
        ['duration_out_of_range'],
        []
      ),
      IF(
        trip_distance IS NULL
          OR IS_NAN(trip_distance)
          OR IS_INF(trip_distance)
          OR trip_distance < 0.1
          OR trip_distance > 100,
        ['distance_out_of_range'],
        []
      ),
      IF(
        total_amount IS NULL OR total_amount <= 0,
        ['non_positive_total'],
        []
      ),
      IF(
        pickup_zone IS NULL OR dropoff_zone IS NULL,
        ['missing_zone_match'],
        []
      ),
      IF(
        COALESCE(payment_type IN (3, 4, 6), FALSE),
        ['excluded_payment_type'],
        []
      ),
      IF(duplicate_rank > 1, ['duplicate'], [])
    ) AS quality_issues
  FROM enriched_rows
)
SELECT
  source_month,
  active_run_id AS run_id,
  pickup_datetime,
  dropoff_datetime,
  service_date,
  pickup_hour,
  day_type,
  pickup_location_id,
  pickup_borough,
  pickup_zone,
  dropoff_location_id,
  dropoff_borough,
  dropoff_zone,
  trip_distance,
  trip_duration_minutes,
  payment_type,
  fare_amount,
  tip_amount,
  total_amount,
  congestion_surcharge,
  airport_fee,
  cbd_congestion_fee,
  quality_issues,
  ARRAY_LENGTH(quality_issues) = 0 AS is_analytics_eligible
FROM issue_rows;

CREATE TEMP TABLE gold_candidate AS
SELECT
  source_month,
  service_date,
  day_type,
  pickup_location_id,
  pickup_hour,
  COUNT(*) AS trip_count,
  SUM(trip_duration_minutes) AS engaged_minutes,
  SUM(trip_distance) AS distance_miles,
  SUM(total_amount) AS gross_receipts
FROM prepared
WHERE is_analytics_eligible
GROUP BY
  source_month,
  service_date,
  day_type,
  pickup_location_id,
  pickup_hour;

BEGIN TRANSACTION;

DELETE FROM `__PROJECT_ID__.taxi_silver.trips`
WHERE source_month = @source_month;

INSERT INTO `__PROJECT_ID__.taxi_silver.trips`
SELECT *
FROM prepared;

DELETE FROM `__PROJECT_ID__.taxi_gold.zone_hour_metrics`
WHERE source_month = @source_month;

INSERT INTO `__PROJECT_ID__.taxi_gold.zone_hour_metrics`
SELECT *
FROM gold_candidate;

COMMIT TRANSACTION;
