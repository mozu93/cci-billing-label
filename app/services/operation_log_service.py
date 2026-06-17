# app/services/operation_log_service.py
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
