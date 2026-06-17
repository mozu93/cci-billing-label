# tests/test_backup_service.py
import os
from app.services.backup_service import create_backup, list_backups


def test_create_backup(tmp_path):
    db_path = str(tmp_path / "test.db")
    with open(db_path, "wb") as f:
        f.write(b"SQLite format 3\x00" + b"\x00" * 100)
    backup_dir = str(tmp_path / "backups")
    result = create_backup(db_path=db_path, backup_dir=backup_dir)
    assert os.path.exists(result)
    assert result.endswith(".db")


def test_list_backups(tmp_path):
    import time
    db_path = str(tmp_path / "test.db")
    with open(db_path, "wb") as f:
        f.write(b"SQLite format 3\x00" + b"\x00" * 100)
    backup_dir = str(tmp_path / "backups")
    create_backup(db_path=db_path, backup_dir=backup_dir)
    time.sleep(1.1)
    create_backup(db_path=db_path, backup_dir=backup_dir)
    backups = list_backups(backup_dir)
    assert len(backups) == 2
