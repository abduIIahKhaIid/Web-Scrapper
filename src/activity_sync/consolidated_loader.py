from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
from loguru import logger

from activity_sync.openai_service import OpenAIService
from activity_sync.settings import Settings
from activity_sync.supabase_repository import SupabaseRepository
from activity_sync.text_utils import (
    clean_int,
    clean_text,
    normalize_activity_name,
    row_hash,
)


class ConsolidatedActivityLoader:
    COL_ACTIVITY_NAME = "activity name"
    COL_ACTIVITY_CODE = "Activity Code"
    COL_DIVISION = "Division"
    COL_GROUP = "Group"
    COL_CLASS = "Class"
    COL_ISIC_DESC = "ISIC Description"
    COL_ACTIVITY_DESC = "Activity Description"
    COL_JURISDICTION = "Jurisdiction"

    def __init__(
        self,
        settings: Settings,
        repository: SupabaseRepository,
        openai_service: OpenAIService,
    ):
        self.settings = settings
        self.repository = repository
        self.openai_service = openai_service

    def load_excel(self) -> pd.DataFrame:
        """
        Load only the Final sheet.

        The Final sheet contains the correct columns:
        activity name, Activity Code, Division, Group, Class,
        ISIC Description, Activity Description, Jurisdiction.
        """
        if not self.settings.consolidated_file.exists():
            raise FileNotFoundError(
                f"Consolidated file not found: {self.settings.consolidated_file}"
            )

        logger.info(
            f"Loading Excel file: {self.settings.consolidated_file}, "
            f"sheet: {self.settings.consolidated_sheet_name}"
        )

        df = pd.read_excel(
            self.settings.consolidated_file,
            sheet_name=self.settings.consolidated_sheet_name,
        )

        df.columns = [str(col).strip() for col in df.columns]

        required = [
            self.COL_ACTIVITY_NAME,
            self.COL_ACTIVITY_CODE,
            self.COL_DIVISION,
            self.COL_GROUP,
            self.COL_CLASS,
            self.COL_ISIC_DESC,
            self.COL_ACTIVITY_DESC,
            self.COL_JURISDICTION,
        ]

        missing = [col for col in required if col not in df.columns]

        if missing:
            raise ValueError(
                f"Missing columns in sheet '{self.settings.consolidated_sheet_name}': {missing}\n"
                f"Available columns: {list(df.columns)}"
            )

        logger.info(f"Final sheet columns: {list(df.columns)}")
        logger.info(f"Total rows in Final sheet: {len(df)}")

        return df

    def build_semantic_text(self, activity_name: str) -> str:
        """
        Semantic search must use only Activity Name.
        Do not include Division, Group, Class, ISIC Description, or Activity Description.
        """
        return activity_name

    def prepare_rows(self, jurisdiction: str) -> List[Dict[str, Any]]:
        df = self.load_excel()

        df[self.COL_JURISDICTION] = df[self.COL_JURISDICTION].apply(clean_text)

        available_jurisdictions = (
            df[self.COL_JURISDICTION]
            .dropna()
            .astype(str)
            .map(clean_text)
            .replace("", pd.NA)
            .dropna()
            .unique()
            .tolist()
        )

        logger.info(
            f"Available jurisdictions in Final sheet: "
            f"{sorted(available_jurisdictions)[:50]}"
        )

        df = df[
            df[self.COL_JURISDICTION].str.lower() == jurisdiction.lower()
        ].copy()

        df["_activity_code_int"] = df[self.COL_ACTIVITY_CODE].apply(clean_int)

        # Only load records that have Activity Code
        df = df[df["_activity_code_int"].notna()].copy()

        logger.info(f"Filtered rows for jurisdiction={jurisdiction}: {len(df)}")

        rows: List[Dict[str, Any]] = []

        for _, row in df.iterrows():
            activity_name = clean_text(row.get(self.COL_ACTIVITY_NAME, ""))
            activity_code = clean_int(row.get(self.COL_ACTIVITY_CODE, ""))

            if not activity_name or activity_code is None:
                continue

            division = clean_int(row.get(self.COL_DIVISION, ""))
            group = clean_int(row.get(self.COL_GROUP, ""))
            class_code = clean_int(row.get(self.COL_CLASS, ""))

            normalized = normalize_activity_name(activity_name)
            semantic_text = self.build_semantic_text(activity_name)

            source_hash = row_hash(
                [
                    "consolidated_final_sheet",
                    jurisdiction,
                    activity_name,
                    activity_code,
                    division,
                    group,
                    class_code,
                ]
            )

            rows.append(
                {
                    "activity_name": activity_name,
                    "activity_name_normalized": normalized,
                    "activity_code": activity_code,
                    "division": division,
                    "activity_group": group,
                    "class_code": class_code,
                    "isic_description": clean_text(row.get(self.COL_ISIC_DESC, "")),
                    "activity_description": clean_text(
                        row.get(self.COL_ACTIVITY_DESC, "")
                    ),
                    "jurisdiction": jurisdiction,
                    "semantic_text": semantic_text,
                    "source": "consolidated_final_sheet",
                    "source_row_hash": source_hash,
                    "status": "Approved",
                    "raw_payload": {
                        "activity_name": activity_name,
                        "activity_code": activity_code,
                        "division": division,
                        "group": group,
                        "class": class_code,
                        "isic_description": clean_text(
                            row.get(self.COL_ISIC_DESC, "")
                        ),
                        "activity_description": clean_text(
                            row.get(self.COL_ACTIVITY_DESC, "")
                        ),
                        "jurisdiction": jurisdiction,
                    },
                }
            )

        unique: Dict[str, Dict[str, Any]] = {}

        for item in rows:
            unique[item["source_row_hash"]] = item

        logger.info(f"Unique rows prepared for {jurisdiction}: {len(unique)}")

        return list(unique.values())

    def upload(self, jurisdiction: str, batch_size: int = 50) -> None:
        rows = self.prepare_rows(jurisdiction=jurisdiction)

        logger.info(f"Rows to upload for {jurisdiction}: {len(rows)}")

        if not rows:
            logger.warning(
                f"No rows found for jurisdiction={jurisdiction}. "
                f"Please check jurisdiction spelling in the Final sheet."
            )
            return

        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]

            texts = [row["semantic_text"] for row in batch]
            embeddings = self.openai_service.create_embeddings(texts)

            for row, embedding in zip(batch, embeddings):
                row["embedding"] = embedding

            self.repository.upsert_activities(batch)

            logger.success(
                f"Uploaded {jurisdiction} rows "
                f"{start + 1} to {min(start + batch_size, len(rows))}"
            )

        logger.success(f"Completed uploading Final sheet data for {jurisdiction}.")