# tests/test_payment_dialog.py
from datetime import date, datetime

from app.services.issuance_service import fiscal_year_of

_THIS_FY = fiscal_year_of(date.today())


def _project(name, fiscal_year, status="active"):
    from app.database.connection import get_session
    from app.services.project_service import create_project
    session = get_session()
    try:
        proj = create_project(session, name, None, fiscal_year, "list")
        proj.status = status   # 旧版で「完了」にした名簿も表示されることの確認用
        session.commit()
        return proj.id
    finally:
        session.close()


def _unpaid_invoice(project_id, name):
    from app.database.connection import get_session
    from app.database.models import Issuance
    session = get_session()
    try:
        session.add(Issuance(project_id=project_id, doc_type="invoice",
                             doc_number=f"INV-{project_id}", status="発行済み",
                             amount=10000, issued_at=datetime.now(),
                             recipient_organization=name))
        session.commit()
    finally:
        session.close()


def _widget(qtbot):
    from app.ui.payment_dialog import PaymentManagementWidget
    w = PaymentManagementWidget()
    qtbot.addWidget(w)
    return w


def _project_names(w):
    return [w._proj_combo.itemText(i) for i in range(1, w._proj_combo.count())]


def test_default_fiscal_year_is_this_year(qtbot, memory_db):
    w = _widget(qtbot)
    assert w._year_combo.currentData() == _THIS_FY
    assert w._year_combo.itemText(0) == "すべての年度"


def test_project_choices_follow_fiscal_year(qtbot, memory_db):
    _project("今年度の名簿", _THIS_FY)
    _project("完了にした今年度の名簿", _THIS_FY, status="closed")
    _project("前年度の名簿", _THIS_FY - 1)
    w = _widget(qtbot)

    assert sorted(_project_names(w)) == ["今年度の名簿", "完了にした今年度の名簿"]

    w._year_combo.setCurrentIndex(w._year_combo.findData(_THIS_FY - 1))
    assert _project_names(w) == ["前年度の名簿"]

    w._year_combo.setCurrentIndex(0)   # すべての年度
    assert len(_project_names(w)) == 3


def test_unpaid_in_earlier_years_is_noted(qtbot, memory_db):
    old = _project("前年度の名簿", _THIS_FY - 1)
    _unpaid_invoice(old, "前年度商店")
    w = _widget(qtbot)
    assert "前年度以前に未入金 1件" in w._earlier_unpaid_label.text()
    assert not w._earlier_unpaid_label.isHidden()

    w._year_combo.setCurrentIndex(0)   # すべての年度なら注意は不要
    assert w._earlier_unpaid_label.isHidden()


def test_no_note_without_earlier_unpaid(qtbot, memory_db):
    w = _widget(qtbot)
    assert w._earlier_unpaid_label.isHidden()


def test_reloads_projects_when_shown_again(qtbot, memory_db):
    """タブを開き直したら名簿の候補を作り直す（起動後に作った名簿も選べる）。"""
    w = _widget(qtbot)
    assert _project_names(w) == []

    _project("2026 視察研修", _THIS_FY)
    w.show()
    assert _project_names(w) == ["2026 視察研修"]


def test_filter_row_fits_780px(qtbot, memory_db):
    """年度を足しても、最小環境の幅780pxで絞り込み欄が右端で切れない。"""
    w = _widget(qtbot)
    w.resize(780, 500)
    w.show()
    qtbot.waitExposed(w)
    for combo in (w._year_combo, w._proj_combo, w._status_combo):
        right = combo.mapTo(w, combo.rect().topRight()).x()
        assert right < 780, f"右端 {right}px が 780px を超えた"
    # 名簿名は欄では省略されても、開いた一覧では読める幅にする
    assert w._proj_combo.view().minimumWidth() >= 400
