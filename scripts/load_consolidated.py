from pathlib import Path
import argparse
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from loguru import logger

from activity_sync.consolidated_loader import ConsolidatedActivityLoader
from activity_sync.openai_service import OpenAIService
from activity_sync.settings import Settings
from activity_sync.supabase_repository import SupabaseRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jurisdiction", required=True)
    args = parser.parse_args()

    settings = Settings.from_env()
    logger.add(settings.logs_dir / "load_consolidated.log", rotation="1 MB", retention=5)

    repository = SupabaseRepository(settings)
    openai_service = OpenAIService(settings)

    loader = ConsolidatedActivityLoader(
        settings=settings,
        repository=repository,
        openai_service=openai_service,
    )

    loader.upload(jurisdiction=args.jurisdiction)


if __name__ == "__main__":
    main()