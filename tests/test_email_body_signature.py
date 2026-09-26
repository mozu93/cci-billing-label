# tests/test_email_body_signature.py
"""メール本文の末尾に、この端末のローカル署名が自動で付く。"""
import app.services.email_service as email_service


def test_body_to_html_appends_signature(monkeypatch):
    monkeypatch.setattr(email_service, "get_email_signature",
                        lambda: "南工会議所 水谷\nTEL 000-000-0000")
    html = email_service.render_body_html("本文です。")
    assert "本文です。" in html
    assert "南工会議所 水谷" in html
    assert "TEL 000-000-0000" in html
    # 本文と署名の間は空行で区切る
    assert "本文です。<br><br>南工会議所 水谷<br>TEL 000-000-0000" in html


def test_body_to_html_without_signature_is_unchanged(monkeypatch):
    monkeypatch.setattr(email_service, "get_email_signature", lambda: "")
    html = email_service.render_body_html("本文です。")
    assert html == (
        "<div style='font-family:sans-serif; font-size:14px; line-height:1.8;'>"
        "本文です。</div>"
    )
