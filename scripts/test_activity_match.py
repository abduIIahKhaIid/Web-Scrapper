from pathlib import Path
import argparse
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from activity_sync.openai_service import OpenAIService
from activity_sync.settings import Settings
from activity_sync.supabase_repository import SupabaseRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jurisdiction", required=True)
    parser.add_argument("--query", required=True)
    args = parser.parse_args()

    settings = Settings.from_env()
    openai_service = OpenAIService(settings)
    repository = SupabaseRepository(settings)

    embedding = openai_service.create_embedding(args.query)

    matches = repository.match_activity_by_name(
        query_embedding=embedding,
        jurisdiction=args.jurisdiction,
        match_count=5,
    )

    print("\nQuery:", args.query)
    print("Jurisdiction:", args.jurisdiction)

    print("\nTop Matches:")
    for match in matches:
        print("-" * 80)
        print("Activity Name:", match.get("activity_name"))
        print("Activity Code:", match.get("activity_code"))
        print("Status:", match.get("status"))
        print("Similarity:", round(float(match.get("similarity", 0)), 4))


if __name__ == "__main__":
    main()