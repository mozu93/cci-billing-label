# app/services/operation_log_service.py
from datetime import datetime

from app.database.models import OperationLog
from app.utils import current_user


def add_log(session, action: str, target_type: str = "",
            target_id: int | None = None, detail: str = "") -> None:
    """操作ログを1件記録する（commitまで行う）。"""
    session.add(OperationLog(
        staff_id=current_user.get_id(),
        staff_name=current_user.get_name(),
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    ))
    session.commit()


def search_logs(session, from_dt: datetime, to_dt: datetime,
                action: str | None = None) -> list[OperationLog]:
    """期間と操作種別で操作ログを絞り込み、新しい順で返す。"""
    query = (session.query(OperationLog)
             .filter(OperationLog.created_at >= from_dt)
             .filter(OperationLog.created_at <= to_dt))
    if action:
        query = query.filter(OperationLog.action == action)
    return query.order_by(OperationLog.created_at.desc()).all()
