# -*- coding: utf-8 -*-
import hashlib
import io
import json
import os

from app.utils.updater import (
    check_latest_version,
    download_new_exe,
    is_newer_version,
)


def test_newer_patch():
    assert is_newer_version("1.0.0", "1.0.1") is True

def test_same_version():
    assert is_newer_version("1.0.0", "1.0.0") is False

def test_older_version():
    assert is_newer_version("1.0.1", "1.0.0") is False

def test_minor_bump():
    assert is_newer_version("1.0.0", "1.1.0") is True

def test_major_bump():
    assert is_newer_version("1.0.0", "2.0.0") is True

def test_v_prefix_stripped():
    assert is_newer_version("1.0.0", "v1.0.1") is True


class _Response(io.BytesIO):
    def __init__(self, content: bytes, headers=None):
        super().__init__(content)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_latest_version_selects_exact_installer_and_digest(monkeypatch):
    digest = "a" * 64
    payload = {
        "tag_name": "v2.2.2",
        "assets": [
            {
                "name": "source.exe",
                "browser_download_url": (
                    "https://github.com/mozu93/cci-billing-label-releases/"
                    "releases/download/v2.2.2/source.exe"),
                "digest": f"sha256:{'b' * 64}",
            },
            {
                "name": "CCIBillingLabel_Setup_2.2.2.exe",
                "browser_download_url": (
                    "https://github.com/mozu93/cci-billing-label-releases/"
                    "releases/download/v2.2.2/"
                    "CCIBillingLabel_Setup_2.2.2.exe"),
                "digest": f"sha256:{digest}",
            },
        ],
    }
    monkeypatch.setattr(
        "app.utils.updater.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(
            json.dumps(payload).encode("utf-8")),
    )

    result = check_latest_version()

    assert result["tag_name"] == "v2.2.2"
    assert result["download_url"].endswith(
        "CCIBillingLabel_Setup_2.2.2.exe")
    assert result["sha256"] == digest


def test_latest_version_rejects_release_without_digest(monkeypatch):
    payload = {
        "tag_name": "v2.2.2",
        "assets": [{
            "name": "CCIBillingLabel_Setup_2.2.2.exe",
            "browser_download_url": (
                "https://github.com/mozu93/cci-billing-label-releases/"
                "releases/download/v2.2.2/"
                "CCIBillingLabel_Setup_2.2.2.exe"),
        }],
    }
    monkeypatch.setattr(
        "app.utils.updater.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(
            json.dumps(payload).encode("utf-8")),
    )

    assert check_latest_version() is None


def test_download_installer_verifies_sha256(monkeypatch):
    content = b"verified installer"
    digest = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(
        "app.utils.updater.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(
            content, {"Content-Length": str(len(content))}),
    )
    url = (
        "https://github.com/mozu93/cci-billing-label-releases/"
        "releases/download/v2.2.2/CCIBillingLabel_Setup_2.2.2.exe")

    path = download_new_exe(url, digest)
    try:
        assert path is not None
        assert open(path, "rb").read() == content
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


def test_download_installer_removes_hash_mismatch(monkeypatch):
    content = b"tampered installer"
    monkeypatch.setattr(
        "app.utils.updater.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(
            content, {"Content-Length": str(len(content))}),
    )
    url = (
        "https://github.com/mozu93/cci-billing-label-releases/"
        "releases/download/v2.2.2/CCIBillingLabel_Setup_2.2.2.exe")

    assert download_new_exe(url, "0" * 64) is None


def test_download_installer_rejects_untrusted_url():
    assert download_new_exe(
        "https://example.com/update.exe", "0" * 64) is None
