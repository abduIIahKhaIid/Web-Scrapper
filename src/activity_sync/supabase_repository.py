from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd
from supabase import Client, create_client

from activity_sync.settings import Settings
from activity_sync.text_utils import clean_int, clean_text, normalize_activity_name


class SupabaseRepository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    def upsert_activities(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return

        self.client.table("activities").upsert(
            rows,
            on_conflict="source_row_hash",
        ).execute()

    def upsert_fetched_activities(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return

        self.client.table("fetched_activities").upsert(
            rows,
            on_conflict="source_row_hash",
        ).execute()

    def fetch_activities_by_jurisdiction(self, jurisdiction: str) -> pd.DataFrame:
        all_rows: List[Dict[str, Any]] = []
        page_size = 1000
        start = 0

        while True:
            end = start + page_size - 1

            response = (
                self.client.table("activities")
                .select(
                    "id, activity_name, activity_name_normalized, activity_code, "
                    "division, activity_group, class_code, "
                    "isic_description, activity_description, jurisdiction, official_code, "
                    "status, match_type, matched_with, match_score, reason"
                )
                .ilike("jurisdiction", jurisdiction)
                .range(start, end)
                .execute()
            )

            rows = response.data or []
            all_rows.extend(rows)

            if len(rows) < page_size:
                break

            start += page_size

        df = pd.DataFrame(all_rows)

        if df.empty:
            return df

        df["activity_name"] = df["activity_name"].apply(clean_text)
        df["activity_name_normalized"] = df["activity_name_normalized"].fillna("").astype(str)
        df["activity_code"] = df["activity_code"].apply(clean_int)

        return df

    def match_activity_by_name(
        self,
        query_embedding: List[float],
        jurisdiction: str,
        match_count: int = 5,
    ) -> List[Dict[str, Any]]:
        response = self.client.rpc(
            "match_activity_by_name",
            {
                "query_embedding": query_embedding,
                "target_jurisdiction": jurisdiction,
                "match_count": match_count,
            },
        ).execute()

        return response.data or []

    def get_next_activity_code(self) -> int:
        response = (
            self.client.table("activities")
            .select("activity_code")
            .not_.is_("activity_code", "null")
            .order("activity_code", desc=True)
            .limit(1)
            .execute()
        )

        rows = response.data or []

        if not rows:
            return 1

        current_max = clean_int(rows[0].get("activity_code"))

        if current_max is None:
            return 1

        return current_max + 1

    def update_activity_name(
        self,
        activity_id: int,
        new_activity_name: str,
        match_type: str,
        matched_with: str,
        match_score: float,
        reason: str,
        openai_decision: Dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        normalized = normalize_activity_name(new_activity_name)

        payload = {
            "activity_name": new_activity_name,
            "activity_name_normalized": normalized,
            "status": "Auto-Updated",
            "match_type": match_type,
            "matched_with": matched_with,
            "match_score": round(float(match_score), 4),
            "reason": reason,
            "openai_decision": openai_decision,
            "updated_at": now,
            "last_checked_at": now,
        }

        self.client.table("activities").update(payload).eq("id", activity_id).execute()

    def insert_reconciliation_result(self, row: Dict[str, Any]) -> None:
        self.client.table("reconciliation_results").insert(row).execute()