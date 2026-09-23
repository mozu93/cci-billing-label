# tests/test_counter_member_number_input.py
"""単発発行：会員番号の入力補完。

以前は候補一覧が Popup の QListWidget で、1桁入力すると一覧がキー入力を
横取りし、2桁目以降が入力欄に入らなかった（固まったように見えた）。
"""
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication


def _seed_members():
    from app.database.connection import get_session
    from app.database.models import Member
    s = get_session()
    for num, org in [("0000001", "一番商店"), ("0000002", "二番商店"),
                     ("0000012", "十二番商店"), ("1200000", "百二十万商店")]:
        s.add(Member(member_number=num, organization_name=org))
    s.commit()
    s.close()


def _make(qtbot):
    from app.ui.issuance_counter import IssuanceCounterWidget
    _seed_members()
    w = IssuanceCounterWidget(doc_type="invoice")
    qtbot.addWidget(w)
    w.resize(1120, 728)
    w.show()
    qtbot.waitExposed(w)
    w._member_number_edit.setFocus()
    return w


def _type(text: str, edit):
    """実際のキー入力と同じく、いまキー入力を受けているウィジェットへ送る。"""
    for ch in text:
        target = QApplication.activePopupWidget() or QApplication.focusWidget() or edit
        QTest.keyClick(target, ch)
        QApplication.processEvents()


def test_can_type_several_digits(qtbot, memory_db):
    w = _make(qtbot)
    _type("0000012", w._member_number_edit)
    assert w._member_number_edit.text() == "0000012"


def test_candidates_list_prefix_matches_first(qtbot, memory_db):
    w = _make(qtbot)
    _type("12", w._member_number_edit)
    # 前方一致（1200000）が先、部分一致（0000012）が後
    assert w._member_number_candidates() == ["1200000", "0000012"]


def test_choosing_candidate_fills_member(qtbot, memory_db):
    w = _make(qtbot)
    _type("00000", w._member_number_edit)
    w._member_number_completer.activated.emit("0000002")
    QApplication.processEvents()
    assert w._org_name.text() == "二番商店"
    assert w._member_number_edit.text() == "0000002"
