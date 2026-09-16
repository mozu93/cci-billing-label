# -*- coding: utf-8 -*-
"""PostgreSQL接続URLが記号入りパスワードでも壊れないことを確認する。"""
import pytest

from app.utils import app_config
from app.database.connection import get_engine


SPECIAL_PASSWORDS = ["p@ss", "pa%73s", "p/ss", "p#ss", "p?ss", "p:ss", "pass word"]


def _configure(monkeypatch, password: str):
    monkeypatch.setattr(app_config, "get_config", lambda: {
        "db_type": "postgresql",
        "host": "db.example.jp",
        "port": 5432,
        "database": "cci",
        "user": "cci_user",
        "password": password,
    })


@pytest.mark.parametrize("password", SPECIAL_PASSWORDS)
def test_db_url_roundtrip(monkeypatch, password):
    _configure(monkeypatch, password)
    url = app_config.get_db_url()

    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    assert parsed.password == password
    assert parsed.host == "db.example.jp"
    assert parsed.port == 5432
    assert parsed.database == "cci"
    assert parsed.username == "cci_user"


@pytest.mark.parametrize("password", SPECIAL_PASSWORDS)
def test_get_engine_receives_original_password(monkeypatch, password):
    _configure(monkeypatch, password)
    captured = {}

    import pg8000.dbapi

    def _fake_connect(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(pg8000.dbapi, "connect", _fake_connect)

    engine = get_engine(app_config.get_db_url())
    engine.pool._creator()

    assert captured["password"] == password
    assert captured["host"] == "db.example.jp"
    assert captured["port"] == 5432
    assert captured["database"] == "cci"
    assert captured["user"] == "cci_user"


def test_sqlite_url_unchanged(monkeypatch):
    monkeypatch.setattr(app_config, "get_config", lambda: {})
    assert app_config.get_db_url().startswith("sqlite:///")
