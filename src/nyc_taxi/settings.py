from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    project_id: str
    project_number: str
    location: str = "us-central1"
    raw_bucket: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        project_id = os.environ.get("GCP_PROJECT_ID", "").strip()
        project_number = os.environ.get("GCP_PROJECT_NUMBER", "").strip()
        if not project_id or not project_number:
            raise RuntimeError("GCP_PROJECT_ID and GCP_PROJECT_NUMBER must be set")

        location = os.environ.get("GCP_LOCATION", "us-central1").strip()
        bucket = os.environ.get("GCP_RAW_BUCKET", "").strip()
        return cls(
            project_id=project_id,
            project_number=project_number,
            location=location,
            raw_bucket=bucket or f"{project_id}-raw-{project_number}",
        )
