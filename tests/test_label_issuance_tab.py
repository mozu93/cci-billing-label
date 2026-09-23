# tests/test_label_issuance_tab.py


def test_reloads_projects_when_shown_again(qtbot, memory_db):
    """タブを開き直したら名簿の候補を読み直す。

    起動後に作った名簿が、アプリを再起動するまで件名コンボに出なかった。
    """
    from app.database.connection import get_session
    from app.services.project_service import create_project
    from app.ui.label_issuance_tab import LabelIssuanceTab

    w = LabelIssuanceTab()
    qtbot.addWidget(w)
    before = w._proj_combo.count()

    session = get_session()
    try:
        create_project(session, "2026 視察研修", None, 2026, "list")
    finally:
        session.close()

    w.show()
    assert w._proj_combo.count() == before + 1
