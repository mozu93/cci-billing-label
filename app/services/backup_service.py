# app/services/backup_service.py
import os
import re
import shutil
from datetime import datetime
from app.utils.app_config import get_db_url, get_config


def get_db_path() -> str | None:
    url = get_db_url()
    if url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "")
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        return path
    return None


def create_backup(db_path: str | None = None,
                  backup_dir: str | None = None) -> str:
    if db_path is None:
        db_path = get_db_path()
    if not db_path or not os.path.exists(db_path):
        raise FileNotFoundError(f"DBファイルが見つかりません: {db_path}")

    if backup_dir is None:
        config = get_config()
        backup_dir = config.get("backup_dir", "")
        if not backup_dir:
            backup_dir = os.path.join(os.path.expanduser("~"), "cci-billing", "backup")

    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"cci_billing_{timestamp}.db")
    shutil.copy2(db_path, backup_path)
    return backup_path


def list_backups(backup_dir: str | None = None) -> list[dict]:
    if backup_dir is None:
        config = get_config()
        backup_dir = config.get("backup_dir", "")
        if not backup_dir:
            backup_dir = os.path.join(os.path.expanduser("~"), "cci-billing", "backup")

    if not os.path.exists(backup_dir):
        return []

    backups = []
    for fname in os.listdir(backup_dir):
        if fname.endswith(".db"):
            fpath = os.path.join(backup_dir, fname)
            stat = os.stat(fpath)
            backups.append({
                "name":       fname,
                "path":       fpath,
                "size":       stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y/%m/%d %H:%M"),
            })
    return sorted(backups, key=lambda x: x["created_at"], reverse=True)


def _parse_backup_datetime(fname: str) -> datetime | None:
    m = re.search(r"(\d{8})_(\d{6})\.db$", fname)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def prune_backups(backup_dir: str | None = None) -> int:
    """世代管理ルールに従って古いバックアップを削除する。削除件数を返す。

    保持ルール:
      0-7日前   → 1日1件
      8-30日前  → 1週1件 (ISO週番号)
      31-365日前 → 1四半期1件
      365日超   → 全削除
    """
    if backup_dir is None:
        config = get_config()
        backup_dir = config.get("backup_dir", "")
        if not backup_dir:
            backup_dir = os.path.join(os.path.expanduser("~"), "cci-billing", "backup")

    if not os.path.exists(backup_dir):
        return 0

    now = datetime.now()

    files: list[tuple[datetime, str]] = []
    for fname in os.listdir(backup_dir):
        if not fname.endswith(".db"):
            continue
        dt = _parse_backup_datetime(fname)
        if dt is not None:
            files.append((dt, os.path.join(backup_dir, fname)))

    # 新しい順に処理。スロットで最初に見た（= 最新の）1件だけ残す
    files.sort(key=lambda x: x[0], reverse=True)

    seen: set[tuple] = set()
    to_delete: list[str] = []

    for dt, fpath in files:
        age_days = (now - dt).days

        if age_days > 365:
            to_delete.append(fpath)
            continue

        if age_days <= 7:
            slot = ("day", dt.strftime("%Y%m%d"))
        elif age_days <= 30:
            iso_year, iso_week, _ = dt.isocalendar()
            slot = ("week", f"{iso_year}W{iso_week:02d}")
        else:
            quarter = (dt.month - 1) // 3
            slot = ("quarter", f"{dt.year}Q{quarter}")

        if slot in seen:
            to_delete.append(fpath)
        else:
            seen.add(slot)

    for fpath in to_delete:
        try:
            os.remove(fpath)
        except OSError:
            pass

    return len(to_delete)


def auto_backup_if_needed(backup_dir: str | None = None) -> str | None:
    """起動時の自動バックアップ。本日分がなければ作成し世代管理を実行する。

    バックアップを作成した場合はそのパスを返す。スキップした場合は None。
    PostgreSQL 構成の場合も None を返す（非対応）。
    """
    db_path = get_db_path()
    if not db_path:
        return None

    if backup_dir is None:
        config = get_config()
        backup_dir = config.get("backup_dir", "")
        if not backup_dir:
            backup_dir = os.path.join(os.path.expanduser("~"), "cci-billing", "backup")

    today_prefix = f"cci_billing_{datetime.now().strftime('%Y%m%d')}"
    if os.path.exists(backup_dir):
        for fname in os.listdir(backup_dir):
            if fname.startswith(today_prefix) and fname.endswith(".db"):
                # 本日分が既にある → 世代管理だけ実行
                prune_backups(backup_dir)
                return None

    path = create_backup(db_path, backup_dir)
    prune_backups(backup_dir)
    return path


def restore_backup(backup_path: str, db_path: str | None = None) -> None:
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"バックアップファイルが見つかりません: {backup_path}")
    if db_path is None:
        db_path = get_db_path()
    if not db_path:
        raise ValueError("復元先DBパスを特定できません（PostgreSQL構成では手動対応が必要です）。")
    shutil.copy2(backup_path, db_path)
