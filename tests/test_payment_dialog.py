# tests/test_payment_dialog.py


def test_reloads_projects_when_shown_again(qtbot, memory_db):
    """タブを開き直したら名簿コンボを作り直す。

    起動後に名簿を受付中へ戻しても、コンボが起動時のままで選べなかった。
    名簿一覧が「請求書を発行」タブには出るのに入金管理には出ない、という
    食い違いになる（あちらは showEvent で作り直している）。
    """
    from app.database.connection import get_session
    from app.services.project_service import (
        create_project, close_project, reopen_project,
    )
    from app.ui.payment_dialog import PaymentManagementWidget

    session = get_session()
    try:
        proj = create_project(session, "2026 視察研修", None, 2026, "list")
        project_id = proj.id
        close_project(session, project_id)
    finally:
        session.close()

    w = PaymentManagementWidget()
    qtbot.addWidget(w)
    # 完了済みなので、この時点の候補は「すべて」だけ。
    assert w._proj_combo.count() == 1

    session = get_session()
    try:
        reopen_project(session, project_id)
    finally:
        session.close()

    w.show()
    assert w._proj_combo.count() == 2
    assert w._proj_combo.itemText(1) == "2026 視察研修"
