# tests/test_backup_service.py
import os
import sqlite3
import pytest
from app.services.backup_service import (
    create_backup, list_backups, restore_backup)


def _create_sqlite(path, value="保存データ"):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")
        connection.execute(
            "INSERT INTO sample (value) VALUES (?)", (value,))
        connection.commit()


def test_create_backup(tmp_path):
    db_path = str(tmp_path / "test.db")
    _create_sqlite(db_path)
    backup_dir = str(tmp_path / "backups")
    result = create_backup(db_path=db_path, backup_dir=backup_dir)
    assert os.path.exists(result)
    assert result.endswith(".db")
    with sqlite3.connect(result) as backup:
        assert backup.execute(
            "SELECT value FROM sample").fetchone()[0] == "保存データ"
        assert backup.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_list_backups(tmp_path):
    import time
    db_path = str(tmp_path / "test.db")
    _create_sqlite(db_path)
    backup_dir = str(tmp_path / "backups")
    create_backup(db_path=db_path, backup_dir=backup_dir)
    time.sleep(1.1)
    create_backup(db_path=db_path, backup_dir=backup_dir)
    backups = list_backups(backup_dir)
    assert len(backups) == 2


def test_restore_rejects_corrupt_backup_without_overwriting(tmp_path):
    destination = tmp_path / "current.db"
    _create_sqlite(destination, "現在データ")
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a sqlite database")

    with pytest.raises(ValueError, match="破損"):
        restore_backup(str(corrupt), str(destination))

    with sqlite3.connect(destination) as current:
        assert current.execute(
            "SELECT value FROM sample").fetchone()[0] == "現在データ"
