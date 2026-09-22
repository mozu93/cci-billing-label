# tests/test_config_migration.py
"""旧アプリ(cci-billing)のデータディレクトリからの引き継ぎ。"""
from app.utils.app_config import migrate_legacy_data


def test_migrates_when_only_legacy_exists(tmp_path):
    legacy = tmp_path / ".cci-billing"
    legacy.mkdir()
    (legacy / "config.json").write_text('{"db_configured": true}',
                                        encoding="utf-8")
    (legacy / "m365_token_cache.bin").write_bytes(b"TOKEN")
    new = tmp_path / ".cci-billing-label"

    assert migrate_legacy_data(new, legacy) is True
    assert (new / "config.json").read_text(encoding="utf-8") == \
        '{"db_configured": true}'
    assert (new / "m365_token_cache.bin").read_bytes() == b"TOKEN"


def test_keeps_legacy_dir_after_migration(tmp_path):
    """問題があれば戻せるよう、旧ディレクトリは消さない。"""
    legacy = tmp_path / ".cci-billing"
    legacy.mkdir()
    (legacy / "config.json").write_text("{}", encoding="utf-8")
    new = tmp_path / ".cci-billing-label"

    migrate_legacy_data(new, legacy)

    assert legacy.exists()
    assert (legacy / "config.json").exists()


def test_does_not_migrate_when_already_configured(tmp_path):
    """移行は一度だけ。設定済みなら何もしない。"""
    legacy = tmp_path / ".cci-billing"
    legacy.mkdir()
    (legacy / "config.json").write_text('{"from": "legacy"}', encoding="utf-8")
    new = tmp_path / ".cci-billing-label"
    new.mkdir()
    (new / "config.json").write_text('{"from": "new"}', encoding="utf-8")

    assert migrate_legacy_data(new, legacy) is False
    assert (new / "config.json").read_text(encoding="utf-8") == \
        '{"from": "new"}'


def test_migrates_even_if_new_dir_was_created_by_logger(tmp_path):
    """ログ初期化が先に走って空のディレクトリができていても引き継ぐ。

    applog がトップレベルの get_logger() で CONFIG_DIR.mkdir() するため、
    ディレクトリの存在は「移行済み」を意味しない。
    """
    legacy = tmp_path / ".cci-billing"
    legacy.mkdir()
    (legacy / "config.json").write_text('{"db_configured": true}',
                                        encoding="utf-8")
    new = tmp_path / ".cci-billing-label"
    new.mkdir()
    (new / "app.log").write_text("起動ログ", encoding="utf-8")

    assert migrate_legacy_data(new, legacy) is True
    assert (new / "config.json").exists()


def test_does_not_overwrite_existing_files(tmp_path):
    """新側に既にあるファイルは、旧側のもので上書きしない。"""
    legacy = tmp_path / ".cci-billing"
    legacy.mkdir()
    (legacy / "config.json").write_text('{"from": "legacy"}', encoding="utf-8")
    (legacy / "cci_billing.db").write_bytes(b"OLD")
    new = tmp_path / ".cci-billing-label"
    new.mkdir()
    (new / "cci_billing.db").write_bytes(b"CURRENT")

    assert migrate_legacy_data(new, legacy) is True
    assert (new / "cci_billing.db").read_bytes() == b"CURRENT"
    assert (new / "config.json").exists()


def test_does_nothing_when_legacy_has_no_config(tmp_path):
    """旧側にディレクトリだけあって設定が無いなら、引き継ぐものはない。"""
    legacy = tmp_path / ".cci-billing"
    legacy.mkdir()
    new = tmp_path / ".cci-billing-label"

    assert migrate_legacy_data(new, legacy) is False


def test_does_nothing_when_neither_exists(tmp_path):
    new = tmp_path / ".cci-billing-label"
    legacy = tmp_path / ".cci-billing"

    assert migrate_legacy_data(new, legacy) is False
    assert not new.exists()
