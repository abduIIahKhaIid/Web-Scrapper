from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import httpx
import pandas as pd
from loguru import logger

from activity_sync.settings import Settings
from activity_sync.text_utils import clean_text, normalize_activity_name, row_hash


class MeydanApiClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def headers(self) -> Dict[str, str]:
        if not self.settings.meydan_api_key:
            raise RuntimeError("MEYDAN_API_KEY is missing in .env")

        bearer = self.settings.meydan_bearer_token or self.settings.meydan_api_key

        return {
            "apikey": self.settings.meydan_api_key,
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/json",
        }

    def fetch_page(self, offset: int, limit: int) -> List[Dict[str, Any]]:
        params = {
            "select": "*",
            "order": "Code.asc",
            "offset": str(offset),
            "limit": str(limit),
        }

        with httpx.Client(timeout=60) as client:
            response = client.get(
                self.settings.meydan_api_url,
                headers=self.headers(),
                params=params,
            )

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, list):
                raise RuntimeError(f"Unexpected API response: {data}")

            return data

    def fetch_all(self, limit: int = 1000, max_pages: int = 20) -> List[Dict[str, Any]]:
        all_rows: List[Dict[str, Any]] = []

        for page in range(max_pages):
            offset = page * limit

            logger.info(f"Fetching Meydan API offset={offset}, limit={limit}")

            rows = self.fetch_page(offset=offset, limit=limit)

            logger.info(f"Fetched rows: {len(rows)}")

            if not rows:
                break

            all_rows.extend(rows)

            if len(rows) < limit:
                break

        return all_rows

    def normalize_api_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        activity_name = clean_text(row.get("Activity Name", ""))
        official_code = clean_text(row.get("Code", ""))

        return {
            "jurisdiction": "Meydan",
            "source_type": "api",
            "official_code": official_code,
            "activity_name": activity_name,
            "activity_name_normalized": normalize_activity_name(activity_name),
            "official_category": clean_text(row.get("Category", "")),
            "official_status": clean_text(row.get("Status", "")),
            "official_risk_rating": clean_text(row.get("Risk Rating", "")),
            "official_industry_risk": clean_text(row.get("Industry Risk", "")),
            "official_dnfbp": clean_text(row.get("DNFBP", "")),
            "official_third_party": clean_text(row.get("Third Party", "")),
            "official_when": clean_text(row.get("When", "")),
            "official_notes": clean_text(row.get("Notes", "")),
            "raw_payload": row,
            "source_row_hash": row_hash(["Meydan", official_code, activity_name]),
        }

    def fetch_save_csv(self) -> pd.DataFrame:
        rows = self.fetch_all()
        normalized = [self.normalize_api_row(row) for row in rows if clean_text(row.get("Activity Name", ""))]

        df = pd.DataFrame(normalized)

        output_path = self.settings.fetched_dir / "meydan_api_activities.csv"
        df.to_csv(output_path, index=False, encoding="utf-8-sig")

        logger.success(f"Meydan API data saved: {output_path}")
        logger.success(f"Total Meydan API rows: {len(df)}")

        return df