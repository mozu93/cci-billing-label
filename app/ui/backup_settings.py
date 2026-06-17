# app/ui/backup_settings.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QGroupBox, QHeaderView, QFileDialog, QLabel
)
from PyQt6.QtCore import Qt
from app.utils.app_config import get_config, save_config
from app.services.backup_service import create_backup, list_backups, restore_backup, get_db_path


class BackupSettingsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def showEvent(self, event):
        # 画面を開くたびにバックアップ一覧を最新化する（更新ボタン不要）
        super().showEvent(event)
        self._load_list()

    def _build(self):
        layout = QVBoxLayout(self)
        grp = QGroupBox("バックアップ設定")
        form = QFormLayout(grp)
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)
        self._backup_dir = QLineEdit()
        self._backup_dir.setPlaceholderText("バックアップ保存先フォルダ")
        btn_browse = QPushButton("参照")
        btn_browse.clicked.connect(self._browse)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self._backup_dir)
        dir_row.addWidget(btn_browse)
        form.addRow("保存先", dir_row)
        layout.addWidget(grp)
        btn_row = QHBoxLayout()
        btn_save_cfg = QPushButton("設定を保存")
        btn_save_cfg.clicked.connect(self._save_config)
        btn_row.addWidget(btn_save_cfg)
        btn_backup = QPushButton("今すぐバックアップ")
        btn_backup.clicked.connect(self._backup_now)
        btn_row.addWidget(btn_backup)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addWidget(QLabel("バックアップ一覧："))
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["ファイル名", "作成日時", "サイズ"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)
        btn_row2 = QHBoxLayout()
        btn_restore = QPushButton("選択したバックアップを復元")
        btn_restore.clicked.connect(self._restore)
        btn_row2.addWidget(btn_restore)
        btn_row2.addStretch()
        layout.addLayout(btn_row2)

    def _load(self):
        config = get_config()
        self._backup_dir.setText(config.get("backup_dir", ""))
        self._load_list()

    def _load_list(self):
        backups = list_backups()
        self._table.setRowCount(0)
        for b in backups:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(b["name"]))
            self._table.setItem(row, 1, QTableWidgetItem(b["created_at"]))
            size_kb = b["size"] // 1024
            self._table.setItem(row, 2, QTableWidgetItem(f"{size_kb} KB"))
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, b["path"])

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "バックアップ先を選択")
        if d:
            self._backup_dir.setText(d)

    def _save_config(self):
        config = get_config()
        config["backup_dir"] = self._backup_dir.text().strip()
        save_config(config)
        QMessageBox.information(self, "保存", "設定を保存しました。")

    def _backup_now(self):
        db_path = get_db_path()
        if not db_path:
            QMessageBox.warning(self, "非対応", "PostgreSQL構成では自動バックアップに対応していません。")
            return
        try:
            self._save_config()
            path = create_backup()
            QMessageBox.information(self, "完了", f"バックアップしました。\n{path}")
            self._load_list()
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))

    def _restore(self):
        row = self._table.currentRow()
        if row < 0:
            return
        backup_path = self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        ret = QMessageBox.warning(
            self, "復元の確認",
            f"このバックアップから復元しますか？\n\n{backup_path}\n\n"
            "現在のデータはすべて上書きされます。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            restore_backup(backup_path)
            QMessageBox.information(self, "完了", "復元しました。アプリを再起動してください。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
