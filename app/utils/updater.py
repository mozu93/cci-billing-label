# -*- coding: utf-8 -*-
import os
import sys
import json
import hashlib
import hmac
import re
import tempfile
import subprocess
import urllib.request
import urllib.error
from urllib.parse import urlparse
from typing import Optional

from packaging.version import Version

GITHUB_API_URL = "https://api.github.com/repos/mozu93/cci-billing-label/releases/latest"
_TIMEOUT = 8
_RELEASE_PATH_PREFIX = "/mozu93/cci-billing-label/releases/download/"
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def is_newer_version(current: str, latest: str) -> bool:
    """latest が current より新しければ True。v プレフィックスは除去する。"""
    current = current.lstrip("v")
    latest  = latest.lstrip("v")
    return Version(latest) > Version(current)


def check_latest_version() -> Optional[dict]:
    """
    GitHub API で最新リリースを取得する。
    戻り値:
      {"tag_name": "v1.0.1", "download_url": "https://...",
       "sha256": "..."} または None（失敗時）
    """
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "cci-billing-label-updater"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        assets = data.get("assets", [])
        if not tag or not assets:
            return None
        expected_name = (
            f"CCIBillingLabel_Setup_{tag.lstrip('v')}.exe")
        asset = next(
            (item for item in assets
             if item.get("name") == expected_name),
            None,
        )
        if not asset:
            return None
        download_url = asset.get("browser_download_url", "")
        digest = asset.get("digest", "")
        sha256 = (
            digest.removeprefix("sha256:")
            if isinstance(digest, str) else ""
        )
        if (
            not _is_trusted_release_url(download_url)
            or not _SHA256_RE.fullmatch(sha256)
        ):
            return None
        return {
            "tag_name": tag,
            "download_url": download_url,
            "sha256": sha256.lower(),
        }
    except Exception:
        return None


def _is_trusted_release_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "github.com"
            and parsed.path.startswith(_RELEASE_PATH_PREFIX)
            and parsed.path.endswith(".exe")
        )
    except Exception:
        return False


def download_new_exe(
        url: str, expected_sha256: str,
        progress_callback=None) -> Optional[str]:
    """
    新しいインストーラー exe を %TEMP% にダウンロードする。
    progress_callback(received_bytes, total_bytes) を呼び出す（total が不明な場合は -1）。
    GitHub APIが返したSHA-256と一致した場合のみダウンロード先を返す。
    """
    tmp_path = ""
    try:
        if (
            not _is_trusted_release_url(url)
            or not _SHA256_RE.fullmatch(expected_sha256 or "")
        ):
            return None
        req = urllib.request.Request(url, headers={"User-Agent": "cci-billing-label-updater"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", -1))
            fd, tmp_path = tempfile.mkstemp(suffix=".exe", prefix="cci_billing_label_new_")
            received = 0
            digest = hashlib.sha256()
            with os.fdopen(fd, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if progress_callback:
                        progress_callback(received, total)
        if total >= 0 and received != total:
            raise ValueError("ダウンロードサイズが一致しません。")
        if not hmac.compare_digest(
                digest.hexdigest(), expected_sha256.lower()):
            raise ValueError("ダウンロードファイルのSHA-256が一致しません。")
        return tmp_path
    except Exception:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return None


def launch_updater(new_exe_path: str, current_exe_path: str):
    """
    updater.bat を %TEMP% に生成して起動し、アプリを終了する。
    bat は: 3秒待機（アプリ終了を待つ）→ インストーラーを起動 → 自己削除
    """
    bat_fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="cci_billing_label_updater_")
    with os.fdopen(bat_fd, "w", encoding="cp932") as f:
        f.write("@echo off\r\n")
        f.write("timeout /t 3 /nobreak > nul\r\n")
        f.write(f'start "" "{new_exe_path}"\r\n')
        f.write('del "%~f0"\r\n')
    subprocess.Popen(["cmd", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(0)
