# -*- coding: utf-8 -*-
"""操作ログの検索条件を確認する。"""
from datetime import datetime

from app.database.models import OperationLog
from app.services.operation_log_service import search_logs


def _add(session, action: str, when: datetime, detail: str = ""):
    log = OperationLog(action=action, detail=detail, staff_name="担当A")
    session.add(log)
    session.commit()
    # created_at は既定値で入るため、テスト用に上書きする。
    log.created_at = when
    session.commit()
    return log


def test_filters_by_period(db_session):
    _add(db_session, "発行", datetime(2026, 5, 1, 10, 0, 0))
    _add(db_session, "発行", datetime(2026, 6, 1, 10, 0, 0))
    rows = search_logs(db_session,
                       datetime(2026, 5, 1, 0, 0, 0),
                       datetime(2026, 5, 31, 23, 59, 59))
    assert len(rows) == 1


def test_period_boundaries_are_inclusive(db_session):
    _add(db_session, "発行", datetime(2026, 5, 1, 0, 0, 0))
    _add(db_session, "発行", datetime(2026, 5, 31, 23, 59, 59))
    rows = search_logs(db_session,
                       datetime(2026, 5, 1, 0, 0, 0),
                       datetime(2026, 5, 31, 23, 59, 59))
    assert len(rows) == 2


def test_filters_by_action(db_session):
    _add(db_session, "発行", datetime(2026, 5, 10, 10, 0, 0))
    _add(db_session, "入金記録", datetime(2026, 5, 11, 10, 0, 0))
    rows = search_logs(db_session,
                       datetime(2026, 5, 1, 0, 0, 0),
                       datetime(2026, 5, 31, 23, 59, 59),
                       action="入金記録")
    assert [r.action for r in rows] == ["入金記録"]


def test_action_none_returns_all(db_session):
    """画面の「すべて」は action=None で渡す。"""
    _add(db_session, "発行", datetime(2026, 5, 10, 10, 0, 0))
    _add(db_session, "入金記録", datetime(2026, 5, 11, 10, 0, 0))
    rows = search_logs(db_session,
                       datetime(2026, 5, 1, 0, 0, 0),
                       datetime(2026, 5, 31, 23, 59, 59),
                       action=None)
    assert len(rows) == 2


def test_newest_first(db_session):
    _add(db_session, "古い", datetime(2026, 5, 1, 10, 0, 0))
    _add(db_session, "新しい", datetime(2026, 5, 20, 10, 0, 0))
    rows = search_logs(db_session,
                       datetime(2026, 5, 1, 0, 0, 0),
                       datetime(2026, 5, 31, 23, 59, 59))
    assert [r.action for r in rows] == ["新しい", "古い"]
