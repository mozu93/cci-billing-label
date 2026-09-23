# tests/test_test_mail_content.py
"""請求書メールの試し送信：本番と同じテンプレートに【テスト】と注意書きを付ける。"""
from app.database.models import CompanySettings, Issuance
from app.services.issuance_service import build_preview_issuance

_LINES = [{"item_template_id": None, "item_name": "年会費", "quantity": 1,
           "unit": "式", "unit_price": 10000, "tax_rate": 10}]


def test_test_mail_uses_template_with_marks(db_session, monkeypatch):
    import app.services.email_service as es
    from app.services.email_service import build_test_issuance_email
    db_session.add(CompanySettings(name="四日市商工会議所", is_default=True))
    db_session.commit()
    monkeypatch.setattr(es, "get_email_template",
                        lambda kind, template_id=None:
                        ("{書類名}送付のご案内（{文書番号}）",
                         "{宛名} 様\n{件名}の{書類名}（{金額}）をお送りします。\n{会社名}"))

    iss = build_preview_issuance(_LINES, "invoice",
                                 recipient_organization="○○商店",
                                 recipient_name="山田太郎")
    subject, body_html = build_test_issuance_email(db_session, iss, project_name="直接発行")

    assert subject == "【テスト】請求書送付のご案内（（プレビュー））"
    assert body_html.index("これはテスト送信です") < body_html.index("○○商店")
    assert "請求書は発行されていません" in body_html
    assert "直接発行の請求書（¥10,000）" in body_html
    assert "四日市商工会議所" in body_html
    assert db_session.query(Issuance).count() == 0
