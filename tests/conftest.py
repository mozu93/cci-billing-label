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
