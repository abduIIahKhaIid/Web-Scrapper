from pathlib import Path
import argparse
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from loguru import logger

from activity_sync.jurisdiction_reconciler import JurisdictionReconciler
from activity_sync.openai_service import OpenAIService
from activity_sync.settings import Settings
from activity_sync.supabase_repository import SupabaseRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jurisdiction", required=True)
    parser.add_argument("--fetched-csv", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-openai", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    logger.add(settings.logs_dir / "reconciliation.log", rotation="1 MB", retention=5)

    repository = SupabaseRepository(settings)
    openai_service = OpenAIService(settings)

    reconciler = JurisdictionReconciler(
        settings=settings,
        repository=repository,
        openai_service=openai_service,
    )

    reconciler.run(
        jurisdiction=args.jurisdiction,
        fetched_csv_path=args.fetched_csv,
        apply_updates=args.apply,
        use_openai=not args.no_openai,
    )


if __name__ == "__main__":
    main()