# app/utils/app_config.py
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".cci-billing"
CONFIG_FILE = CONFIG_DIR / "config.json"


def get_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {}


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_first_run() -> bool:
    return not CONFIG_FILE.exists() or not get_config().get("db_configured")


def get_db_url() -> str:
    config = get_config()
    if config.get("db_type") == "postgresql":
        host = config["host"]
        port = config.get("port", 5432)
        database = config["database"]
        user = config["user"]
        password = config["password"]
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    db_path = CONFIG_DIR / "cci_billing.db"
    CONFIG_DIR.mkdir(exist_ok=True)
    return f"sqlite:///{db_path}"
