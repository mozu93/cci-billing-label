# tests/test_admin_notification_thread.py
"""所属長への発行通知メール：送信後・送信中にアプリを閉じても落ちず、送信は完了すること。

以前は QThread を quit せずに放置していたため、通知を1回でも送ると
アプリ終了時に "Destroyed while thread is still running" で強制終了（0xC0000409）していた。
落ちるとテストプロセスごと巻き込むので、別プロセスで確認する。
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_SCRIPT = textwrap.dedent("""
    import os, sys, time
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, {root!r})

    from app.database.connection import init_db, get_session
    from app.database.models import Staff
    init_db("sqlite:///:memory:")
    s = get_session()
    boss = Staff(name="所属長", email="boss@example.invalid")
    s.add(boss); s.flush()
    me = Staff(name="担当者", supervisor_id=boss.id)
    s.add(me); s.commit()
    my_id = me.id
    s.close()

    from app.utils import current_user, app_config
    current_user.set_current(my_id, "担当者")
    app_config.get_m365_client_id = lambda: "client"
    app_config.get_m365_tenant_id = lambda: "tenant"

    from app.ui import m365_mail_worker
    def fake_run(self):
        time.sleep({send_sec})   # 認証・送信の代わり
        print("SENT", flush=True)
        self.finished.emit({{}})
    m365_mail_worker.M365MailWorker.run = fake_run

    from PyQt6 import sip
    from PyQt6.QtWidgets import QApplication
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    qapp = QApplication(sys.argv)
    w = IssuanceFromProjectWidget("invoice")
    w._send_admin_notification(
        [{{"doc_number": "INV-1", "recipient": "○○商店", "amount": 1000}}])
    end = time.time() + {wait_sec}
    while time.time() < end:
        qapp.processEvents(); time.sleep(0.02)
    sip.delete(w)          # アプリ終了で画面が破棄される
    print("CLOSED", flush=True)
""")


def _run(send_sec: float, wait_sec: float):
    script = _SCRIPT.format(root=str(_ROOT), send_sec=send_sec, wait_sec=wait_sec)
    return subprocess.run([sys.executable, "-c", script],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60, env=dict(os.environ))


def test_closing_after_notification_was_sent_does_not_crash():
    p = _run(send_sec=0.1, wait_sec=0.5)
    assert p.returncode == 0, f"returncode={p.returncode & 0xFFFFFFFF:#x}\n{p.stderr}"
    assert "SENT" in p.stdout and "CLOSED" in p.stdout


def test_closing_while_sending_waits_for_the_mail_to_be_sent():
    p = _run(send_sec=1.0, wait_sec=0.1)
    assert p.returncode == 0, f"returncode={p.returncode & 0xFFFFFFFF:#x}\n{p.stderr}"
    # 画面は先に閉じるが、通知メールは失われずに送り終えてからプロセスが終わる
    assert p.stdout.index("CLOSED") < p.stdout.index("SENT")
