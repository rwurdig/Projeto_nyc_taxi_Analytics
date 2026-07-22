CREATE TABLE IF NOT EXISTS `__PROJECT_ID__.taxi_ops.monthly_loads` (
  run_id STRING NOT NULL,
  source_month DATE NOT NULL,
  status STRING NOT NULL,
  source_url STRING NOT NULL,
  gcs_uri STRING,
  row_count INT64,
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP,
  message STRING
)
PARTITION BY DATE_TRUNC(source_month, MONTH)
CLUSTER BY status;

CREATE TABLE IF NOT EXISTS `__PROJECT_ID__.taxi_silver.taxi_zones` (
  location_id INT64 NOT NULL,
  borough STRING NOT NULL,
  zone_name STRING NOT NULL,
  service_zone STRING NOT NULL
);

CREATE TABLE IF NOT EXISTS `__PROJECT_ID__.taxi_silver.trips` (
  source_month DATE NOT NULL,
  run_id STRING NOT NULL,
  pickup_datetime DATETIME,
  dropoff_datetime DATETIME,
  service_date DATE,
  pickup_hour INT64,
  day_type STRING,
  pickup_location_id INT64,
  pickup_borough STRING,
  pickup_zone STRING,
  dropoff_location_id INT64,
  dropoff_borough STRING,
  dropoff_zone STRING,
  trip_distance FLOAT64,
  trip_duration_minutes FLOAT64,
  payment_type INT64,
  fare_amount NUMERIC,
  tip_amount NUMERIC,
  total_amount NUMERIC,
  congestion_surcharge NUMERIC,
  airport_fee NUMERIC,
  cbd_congestion_fee NUMERIC,
  quality_issues ARRAY<STRING>,
  is_analytics_eligible BOOL NOT NULL
)
PARTITION BY DATE_TRUNC(source_month, MONTH)
CLUSTER BY pickup_location_id, pickup_hour
OPTIONS (
  require_partition_filter = TRUE
);

CREATE TABLE IF NOT EXISTS `__PROJECT_ID__.taxi_gold.zone_hour_metrics` (
  source_month DATE NOT NULL,
  service_date DATE NOT NULL,
  day_type STRING NOT NULL,
  pickup_location_id INT64 NOT NULL,
  pickup_hour INT64 NOT NULL,
  trip_count INT64 NOT NULL,
  engaged_minutes FLOAT64 NOT NULL,
  distance_miles FLOAT64 NOT NULL,
  gross_receipts NUMERIC NOT NULL
)
PARTITION BY DATE_TRUNC(source_month, MONTH)
CLUSTER BY pickup_location_id, pickup_hour
OPTIONS (
  require_partition_filter = TRUE
);
