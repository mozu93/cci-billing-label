def test_build_preview_issuance(db_session):
    """プレビュー用Issuanceは宛先空・明細合計を持ち、DBに保存されない。"""
    from app.utils.pdf_helpers import build_preview_issuance
    from app.database.models import Issuance
    lines = [{"item_template_id": None, "item_name": "会費",
              "quantity": 2, "unit": "口", "unit_price": 3000, "tax_rate": 0}]
    iss = build_preview_issuance(lines, "invoice")
    assert iss.recipient_organization == ""
    assert iss.recipient_name == ""
    assert iss.doc_type == "invoice"
    assert int(iss.amount) == 6000
    assert len(iss.lines) == 1
    assert iss.lines[0].item_name == "会費"
    # セッションに追加していない＝永続化されていない
    assert db_session.query(Issuance).count() == 0
