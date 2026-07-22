from __future__ import annotations

import argparse
import shutil
import tempfile
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from google.cloud import bigquery, storage

from nyc_taxi.months import YearMonth, completed_months, source_url
from nyc_taxi.settings import Settings

MAX_BYTES_BILLED = 10 * 1024**3
DATASETS = ("taxi_staging", "taxi_ops", "taxi_silver", "taxi_gold")
REQUIRED_COLUMNS = {
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "trip_distance",
    "PULocationID",
    "DOLocationID",
    "payment_type",
    "fare_amount",
    "tip_amount",
    "total_amount",
}


class SourceNotFound(RuntimeError):
    pass


def object_name(month: YearMonth) -> str:
    return f"yellow/source_month={month}/yellow_tripdata_{month}.parquet"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        bigquery_client: Any | None = None,
        storage_client: Any | None = None,
        opener: Callable[..., Any] = urllib.request.urlopen,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.settings = settings
        self.bigquery = bigquery_client or bigquery.Client(
            project=settings.project_id, location=settings.location
        )
        self.storage = storage_client or storage.Client(project=settings.project_id)
        self.opener = opener
        self.today = today

    @property
    def manifest_table(self) -> str:
        return f"{self.settings.project_id}.taxi_ops.monthly_loads"

    def setup(self) -> None:
        self._ensure_bucket()
        for name in DATASETS:
            dataset = bigquery.Dataset(f"{self.settings.project_id}.{name}")
            dataset.location = self.settings.location
            self.bigquery.create_dataset(dataset, exists_ok=True)
        self._run_sql_resource("tables.sql")
        self._load_zones()
        print(f"setup complete in {self.settings.project_id}")

    def _ensure_bucket(self) -> None:
        bucket = self.storage.lookup_bucket(self.settings.raw_bucket)
        if bucket is None:
            bucket = self.storage.bucket(self.settings.raw_bucket)
            bucket.iam_configuration.uniform_bucket_level_access_enabled = True
            bucket.iam_configuration.public_access_prevention = "enforced"
            self.storage.create_bucket(bucket, location=self.settings.location)
            return
        if bucket.location.lower() != self.settings.location.lower():
            raise RuntimeError(
                f"bucket {bucket.name} is in {bucket.location}, expected "
                f"{self.settings.location}"
            )

    def _load_zones(self) -> None:
        table_id = f"{self.settings.project_id}.taxi_silver.taxi_zones"
        config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            schema=[
                bigquery.SchemaField("location_id", "INTEGER"),
                bigquery.SchemaField("borough", "STRING"),
                bigquery.SchemaField("zone_name", "STRING"),
                bigquery.SchemaField("service_zone", "STRING"),
            ],
        )
        zone_file = resources.files("nyc_taxi").joinpath("data", "taxi_zone_lookup.csv")
        with resources.as_file(zone_file) as path, path.open("rb") as source:
            self.bigquery.load_table_from_file(
                source, table_id, job_config=config, location=self.settings.location
            ).result()
        if self.bigquery.get_table(table_id).num_rows != 265:
            raise RuntimeError("taxi zone lookup must contain 265 rows")

    def has_success(self, month: YearMonth) -> bool:
        sql = f"""
            SELECT 1 FROM `{self.manifest_table}`
            WHERE source_month = @source_month AND status = 'SUCCEEDED'
            LIMIT 1
        """
        rows = self.bigquery.query(
            sql,
            job_config=self._query_config(month),
            location=self.settings.location,
        ).result()
        return next(iter(rows), None) is not None

    def load_month(self, month: YearMonth, force: bool = False) -> str:
        run_id = uuid.uuid4().hex
        gcs_uri = f"gs://{self.settings.raw_bucket}/{object_name(month)}"
        if self.has_success(month) and not force:
            now = _utcnow()
            self._insert_attempt(
                run_id,
                month,
                "SKIPPED",
                gcs_uri,
                now,
                now,
                "successful load already exists",
            )
            print(f"{month}: SKIPPED")
            return "SKIPPED"

        self._insert_attempt(run_id, month, "RUNNING", gcs_uri, _utcnow())
        try:
            self._prepare_raw(month, force)
            staging_table, row_count = self._stage(month, run_id, gcs_uri)
            self.transform_month(month, staging_table)
            self._finish_attempt(run_id, "SUCCEEDED", row_count, "load complete")
        except Exception as exc:
            self._finish_attempt(run_id, "FAILED", None, str(exc)[:1000])
            raise
        print(f"{month}: SUCCEEDED ({row_count:,} rows)")
        return "SUCCEEDED"

    def _prepare_raw(self, month: YearMonth, force: bool) -> None:
        bucket = self.storage.bucket(self.settings.raw_bucket)
        blob = bucket.blob(object_name(month))
        if blob.exists(client=self.storage) and not force:
            return
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, f"yellow_tripdata_{month}.parquet")
            self._download(source_url(month), path)
            blob.upload_from_filename(path, content_type="application/octet-stream")

    def _download(self, url: str, path: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "nyc-taxi/0.1"})
        try:
            with (
                self.opener(request, timeout=60) as response,
                path.open("wb") as output,
            ):
                shutil.copyfileobj(response, output, length=1024 * 1024)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise SourceNotFound(f"source not published: {url}") from exc
            raise
        with path.open("rb") as source:
            if source.read(4) != b"PAR1":
                raise RuntimeError("downloaded source is not Parquet")
            source.seek(-4, 2)
            if source.read(4) != b"PAR1":
                raise RuntimeError("downloaded source is incomplete")

    def _stage(self, month: YearMonth, run_id: str, gcs_uri: str) -> tuple[str, int]:
        table_id = (
            f"{self.settings.project_id}.taxi_staging."
            f"yellow_{month.year:04d}{month.month:02d}_{run_id[:8]}"
        )
        config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            autodetect=True,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        self.bigquery.load_table_from_uri(
            gcs_uri, table_id, job_config=config, location=self.settings.location
        ).result()
        table = self.bigquery.get_table(table_id)
        columns = {field.name for field in table.schema}
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise RuntimeError(f"missing required columns: {', '.join(missing)}")
        table.expires = _utcnow() + timedelta(hours=24)
        self.bigquery.update_table(table, ["expires"])
        return table_id, int(table.num_rows)

    def transform_month(self, month: YearMonth, staging_table: str) -> None:
        self._run_sql_resource(
            "transform_month.sql",
            replacements={"STAGING_TABLE": staging_table},
            job_config=self._query_config(month),
        )

    def discover(self, lookback: int) -> None:
        for month in completed_months(self.today(), lookback):
            try:
                self.load_month(month)
            except SourceNotFound:
                print(f"{month}: not published")

    def _insert_attempt(
        self,
        run_id: str,
        month: YearMonth,
        status: str,
        gcs_uri: str,
        started_at: datetime,
        finished_at: datetime | None = None,
        message: str | None = None,
    ) -> None:
        sql = f"""
            INSERT INTO `{self.manifest_table}`
              (run_id, source_month, status, source_url, gcs_uri,
               started_at, finished_at, message)
            VALUES
              (@run_id, @source_month, @status, @source_url, @gcs_uri,
               @started_at, @finished_at, @message)
        """
        config = bigquery.QueryJobConfig(
            maximum_bytes_billed=MAX_BYTES_BILLED,
            query_parameters=[
                bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
                bigquery.ScalarQueryParameter("source_month", "DATE", month.first_day),
                bigquery.ScalarQueryParameter("status", "STRING", status),
                bigquery.ScalarQueryParameter(
                    "source_url", "STRING", source_url(month)
                ),
                bigquery.ScalarQueryParameter("gcs_uri", "STRING", gcs_uri),
                bigquery.ScalarQueryParameter("started_at", "TIMESTAMP", started_at),
                bigquery.ScalarQueryParameter("finished_at", "TIMESTAMP", finished_at),
                bigquery.ScalarQueryParameter("message", "STRING", message),
            ],
        )
        self.bigquery.query(
            sql, job_config=config, location=self.settings.location
        ).result()

    def _finish_attempt(
        self, run_id: str, status: str, row_count: int | None, message: str
    ) -> None:
        sql = f"""
            UPDATE `{self.manifest_table}`
            SET status = @status, row_count = @row_count,
                finished_at = CURRENT_TIMESTAMP(), message = @message
            WHERE run_id = @run_id
        """
        config = bigquery.QueryJobConfig(
            maximum_bytes_billed=MAX_BYTES_BILLED,
            query_parameters=[
                bigquery.ScalarQueryParameter("status", "STRING", status),
                bigquery.ScalarQueryParameter("row_count", "INT64", row_count),
                bigquery.ScalarQueryParameter("message", "STRING", message),
                bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
            ],
        )
        self.bigquery.query(
            sql, job_config=config, location=self.settings.location
        ).result()

    def _query_config(self, month: YearMonth) -> bigquery.QueryJobConfig:
        return bigquery.QueryJobConfig(
            maximum_bytes_billed=MAX_BYTES_BILLED,
            query_parameters=[
                bigquery.ScalarQueryParameter("source_month", "DATE", month.first_day)
            ],
        )

    def _run_sql_resource(
        self,
        name: str,
        replacements: Mapping[str, str] | None = None,
        job_config: bigquery.QueryJobConfig | None = None,
    ) -> None:
        resource = resources.files("nyc_taxi").joinpath("sql", name)
        if not resource.is_file():
            raise RuntimeError(f"missing SQL resource: {name}")
        sql = resource.read_text(encoding="utf-8")
        values = {"PROJECT_ID": self.settings.project_id}
        values.update(replacements or {})
        for key, value in values.items():
            sql = sql.replace(f"{{{{{key}}}}}", value)
            sql = sql.replace(f"__{key}__", value)
        self.bigquery.query(
            sql,
            job_config=job_config
            or bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED),
            location=self.settings.location,
        ).result()


def dispatch(args: argparse.Namespace) -> int:
    pipeline = Pipeline(Settings.from_env())
    if args.command == "setup":
        pipeline.setup()
    elif args.command == "load":
        pipeline.load_month(args.month, force=args.force)
    elif args.command == "discover":
        pipeline.discover(args.lookback_months)
    else:
        from nyc_taxi.analytics import export_results

        export_results(pipeline.bigquery, pipeline.settings, args.month)
    return 0
