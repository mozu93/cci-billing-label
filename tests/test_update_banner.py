# tests/test_update_banner.py
"""最新版チェック中にバナー（MainWindow）が破棄されても、プロセスが落ちないこと。

以前は QThread で確認していたため、問い合わせ中に破棄されると Qt が
"Destroyed while thread is still running" で強制終了（0xC0000409）していた。
落ちるとテストプロセスごと巻き込むので、別プロセスで確認する。
"""
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_SCRIPT = textwrap.dedent("""
    import os, sys, time
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, {root!r})
    import app.utils.updater as updater

    def slow_check():
        time.sleep(1)        # ネットワークが遅い状況を再現
        # 破棄後に「新しいバージョンあり」が届くケースも確かめる
        return {{"tag_name": "v999.0.0", "download_url": "https://example.invalid/x.exe",
                 "sha256": "0" * 64}}

    updater.check_latest_version = slow_check

    from PyQt6 import sip
    from PyQt6.QtWidgets import QApplication
    from app.ui.update_banner import UpdateBanner
    qapp = QApplication(sys.argv)
    banner = UpdateBanner()
    qapp.processEvents()
    sip.delete(banner)       # 問い合わせ中に破棄する（ウィンドウを閉じたときと同じ）
    end = time.time() + 2    # 確認処理が終わって結果を通知するまで待つ
    while time.time() < end:
        qapp.processEvents()
        time.sleep(0.05)
    print("OK", flush=True)
""")


def test_banner_appears_when_newer_version_found(qtbot, monkeypatch):
    import app.utils.updater as updater
    from app.ui.update_banner import UpdateBanner
    monkeypatch.setattr(updater, "check_latest_version", lambda: {
        "tag_name": "v999.0.0",
        "download_url": "https://example.invalid/x.exe",
        "sha256": "0" * 64,
    })
    banner = UpdateBanner()
    qtbot.addWidget(banner)
    qtbot.waitUntil(lambda: not banner.isHidden(), timeout=3000)
    assert "v999.0.0" in banner._lbl.text()
    assert banner._download_url == "https://example.invalid/x.exe"


_DOWNLOAD_SCRIPT = textwrap.dedent("""
    import os, sys, time
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, {root!r})
    import app.utils.updater as updater
    updater.check_latest_version = lambda: None

    def slow_download(*a, **k):
        time.sleep(3)            # 大きなファイルのダウンロード中を再現
        return None

    updater.download_new_exe = slow_download

    from PyQt6 import sip
    from PyQt6.QtWidgets import QApplication
    from app.ui.update_banner import UpdateBanner
    qapp = QApplication(sys.argv)
    banner = UpdateBanner()
    banner._start_download()
    qapp.processEvents()
    sip.delete(banner)           # ダウンロード中にアプリを閉じる
    qapp.processEvents()
    print("OK", flush=True)
""")


def test_closing_during_download_does_not_crash_or_wait():
    script = _DOWNLOAD_SCRIPT.format(root=str(_ROOT))
    t = time.time()
    p = subprocess.run([sys.executable, "-c", script],
                       capture_output=True, text=True, timeout=60,
                       env=dict(os.environ))
    assert p.returncode == 0, (
        f"returncode={p.returncode & 0xFFFFFFFF:#x}\n{p.stdout}\n{p.stderr}")
    assert "OK" in p.stdout
    # ダウンロードの完了を待たずに終わる（中断してよい）
    assert time.time() - t < 3


def test_download_result_is_shown_in_banner(qtbot, monkeypatch):
    import app.utils.updater as updater
    from app.ui.update_banner import UpdateBanner
    monkeypatch.setattr(updater, "download_new_exe",
                        lambda url, sha, progress_callback=None: "C:/tmp/new.exe")
    banner = UpdateBanner()
    qtbot.addWidget(banner)
    banner._start_download()
    qtbot.waitUntil(lambda: banner._tmp_exe_path == "C:/tmp/new.exe", timeout=3000)
    assert not banner._btn_install.isHidden()


def test_download_failure_is_shown_in_banner(qtbot, monkeypatch):
    import app.utils.updater as updater
    from app.ui.update_banner import UpdateBanner
    monkeypatch.setattr(updater, "download_new_exe",
                        lambda url, sha, progress_callback=None: None)
    banner = UpdateBanner()
    qtbot.addWidget(banner)
    banner._start_download()
    qtbot.waitUntil(lambda: "失敗" in banner._lbl.text(), timeout=3000)
    assert not banner._btn_dl.isHidden()


def test_destroying_banner_during_version_check_does_not_crash():
    script = _SCRIPT.format(root=str(_ROOT))
    p = subprocess.run([sys.executable, "-c", script],
                       capture_output=True, text=True, timeout=60,
                       env=dict(os.environ))
    assert p.returncode == 0, (
        f"returncode={p.returncode & 0xFFFFFFFF:#x}\n{p.stdout}\n{p.stderr}")
    assert "OK" in p.stdout
