from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from loguru import logger

from activity_sync.meydan_api_client import MeydanApiClient
from activity_sync.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    logger.add(settings.logs_dir / "fetch_meydan_api.log", rotation="1 MB", retention=5)

    client = MeydanApiClient(settings)
    client.fetch_save_csv()


if __name__ == "__main__":
    main()