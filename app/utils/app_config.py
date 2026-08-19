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


def get_m365_config() -> dict:
    return get_config().get("m365", {})


def save_m365_config(client_id: str, tenant_id: str,
                     account_username: str | None = None,
                     sender_address: str | None = None,
                     test_recipient: str | None = None,
                     trace_client_secret: str | None = None) -> None:
    config = get_config()
    m365 = dict(config.get("m365", {}))
    m365.update({"client_id": client_id, "tenant_id": tenant_id})
    if account_username is not None:
        m365["account_username"] = account_username
    if sender_address is not None:
        m365["sender_address"] = sender_address
    if test_recipient is not None:
        m365["test_recipient"] = test_recipient
    if trace_client_secret is not None:
        m365["trace_client_secret"] = trace_client_secret
    config["m365"] = m365
    save_config(config)


def get_m365_client_id() -> str:
    return get_m365_config().get("client_id", "")


def get_m365_tenant_id() -> str:
    return get_m365_config().get("tenant_id", "")


def get_m365_account_username() -> str:
    return get_m365_config().get("account_username", "")


def get_m365_sender_address() -> str:
    return get_m365_config().get("sender_address", "")


def get_m365_test_recipient() -> str:
    return get_m365_config().get("test_recipient", "")


def get_m365_trace_client_secret() -> str:
    return get_m365_config().get("trace_client_secret", "")


def get_label_print_offset(layout_key: str) -> tuple[float, float]:
    entry = get_config().get("label_print_offset", {}).get(layout_key, {})
    return entry.get("h_mm", 0.0), entry.get("v_mm", 0.0)


def save_label_print_offset(layout_key: str, h_mm: float, v_mm: float) -> None:
    config = get_config()
    config.setdefault("label_print_offset", {})[layout_key] = {
        "h_mm": h_mm, "v_mm": v_mm,
    }
    save_config(config)


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
