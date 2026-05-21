from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    base_dir: Path

    openai_api_key: str
    openai_embedding_model: str
    embedding_dimensions: int
    openai_tiebreaker_model: str

    supabase_url: str
    supabase_service_role_key: str

    meydan_api_url: str
    meydan_api_key: str
    meydan_bearer_token: str

    consolidated_file: Path
    consolidated_sheet_name: str

    fetched_dir: Path
    output_dir: Path
    logs_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=True)

        base_dir = Path(__file__).resolve().parents[2]

        required = {
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
            "SUPABASE_URL": os.getenv("SUPABASE_URL", ""),
            "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        }

        missing = [key for key, value in required.items() if not value]

        if missing:
            raise RuntimeError(f"Missing environment variables: {missing}")

        fetched_dir = base_dir / "data" / "fetched"
        output_dir = base_dir / "data" / "output"
        logs_dir = base_dir / "logs"

        for folder in [fetched_dir, output_dir, logs_dir]:
            folder.mkdir(parents=True, exist_ok=True)

        return cls(
            base_dir=base_dir,
            openai_api_key=required["OPENAI_API_KEY"],
            openai_embedding_model=os.getenv(
                "OPENAI_EMBEDDING_MODEL",
                "text-embedding-3-small",
            ),
            embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "1536")),
            openai_tiebreaker_model=os.getenv(
                "OPENAI_TIEBREAKER_MODEL",
                "gpt-4o-mini",
            ),
            supabase_url=required["SUPABASE_URL"],
            supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],
            meydan_api_url=os.getenv(
                "MEYDAN_API_URL",
                "https://sb.meydanfz.ae/rest/v1/Activity%20List",
            ),
            meydan_api_key=os.getenv("MEYDAN_API_KEY", ""),
            meydan_bearer_token=os.getenv("MEYDAN_BEARER_TOKEN", ""),
            consolidated_file=base_dir
            / "data"
            / "base"
            / "Consolidated List of Activities.xlsx",
            consolidated_sheet_name=os.getenv("CONSOLIDATED_SHEET_NAME", "Final"),
            fetched_dir=fetched_dir,
            output_dir=output_dir,
            logs_dir=logs_dir,
        )