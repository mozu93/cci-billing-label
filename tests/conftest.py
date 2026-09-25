# tests/conftest.py
import os
# pytest-qt をヘッドレスで動かす（QApplication 生成前に設定する必要がある）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base


@pytest.fixture(autouse=True)
def _no_update_check_network(monkeypatch):
    """MainWindow の UpdateBanner がテスト中に GitHub へ問い合わせないようにする。
    結果がネットワーク状況に左右されないように。個別のテストで上書きしてよい。"""
    import app.utils.updater as updater
    monkeypatch.setattr(updater, "check_latest_version", lambda: None)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_mail_test_mode: テスト送信モードの設定を本来どおり読む")


@pytest.fixture(autouse=True)
def _mail_test_mode_off(request, monkeypatch):
    """開発機でテスト送信モードをオンにしていても、テスト結果が変わらないようにする。

    テスト送信モード自体のテストは real_mail_test_mode マーカーで本来の処理を使う。"""
    if request.node.get_closest_marker("real_mail_test_mode"):
        return
    import app.utils.app_config as app_config
    monkeypatch.setattr(app_config, "get_m365_test_mode", lambda: False)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def memory_db():
    """UIウィジェットが get_session() で参照するグローバルDBを
    in-memory SQLite に初期化する。"""
    from app.database.connection import init_db
    init_db("sqlite:///:memory:")
    yield
