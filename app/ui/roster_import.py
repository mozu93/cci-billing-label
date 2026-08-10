# app/ui/roster_import.py
"""事業名簿向けの取り込みダイアログ（列マッピング方式）。

member_import.MemberImportDialog をベースに、
- マッピング対象を ROSTER_COLUMNS（NO.を含む名簿項目）に変更
- 取り込み先を会員マスタではなく事業名簿（add_roster_entries）に変更
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPlainTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QFileDialog,
    QMessageBox, QHeaderView, QComboBox, QCheckBox, QGroupBox
)
from PyQt6.QtCore import QMimeData, Qt
from PyQt6.QtGui import QColor


class _TsvPasteEdit(QPlainTextEdit):
    """Excelからの貼り付け時にタブ文字を保持するためプレーンテキストのみ受け付ける。"""
    def insertFromMimeData(self, source: QMimeData):
        if source.hasText():
            self.insertPlainText(source.text())
from app.database.connection import get_session
from app.utils.excel_utils import (
    ROSTER_COLUMNS, FIELD_LABELS, REQUIRED_ANY,
    parse_tsv_text_raw, parse_excel_file_raw, column_count,
    guess_mapping_from_header, build_member_rows,
)

HEADERS = [FIELD_LABELS[c] for c in ROSTER_COLUMNS]

_HEADER_ALIASES = {
    "参加者名①": "representative_name",
    "参加者名1": "representative_name",
    "フリガナ①": "representative_kana",
    "フリガナ1": "representative_kana",
    "事業所所在地：郵便番号": "postal_code",
    "事業所所在地:郵便番号": "postal_code",
    "事業所所在地：市区町村番地": "address",
    "事業所所在地:市区町村番地": "address",
    "事業所所在地：マンション・ビル名": "address2",
    "事業所所在地:マンション・ビル名": "address2",
    "事業所電話番号": "phone",
}


def _default_positional_mapping_roster(num_cols: int) -> dict[str, int | None]:
    """ROSTER_COLUMNS 基準で左から順に割り当てた初期マッピング。
    名簿では列0を NO. として扱う。
    """
    return {field: (i if i < num_cols else None)
            for i, field in enumerate(ROSTER_COLUMNS)}


def _guess_mapping_from_header_roster(header_cells: list[str]) -> dict[str, int | None]:
    """見出し行の文字列から ROSTER_COLUMNS のフィールドを推測して割り当てる。"""
    label_to_field = {FIELD_LABELS[f]: f for f in ROSTER_COLUMNS}
    mapping: dict[str, int | None] = {field: None for field in ROSTER_COLUMNS}
    for i, raw in enumerate(header_cells):
        h = (raw or "").strip()
        if h in label_to_field:
            mapping[label_to_field[h]] = i
        elif h.lower() in {"no", "no.", "no．", "ｎｏ", "ｎｏ.", "№"}:
            mapping["roster_no"] = i
        elif h in _HEADER_ALIASES:
            mapping[_HEADER_ALIASES[h]] = i
        elif h in ROSTER_COLUMNS:
            mapping[h] = i
    return mapping


def _looks_like_header(row: list[str]) -> bool:
    """既知の見出しが2項目以上あれば、先頭行を見出しと判定する。"""
    guessed = _guess_mapping_from_header_roster(row)
    return sum(index is not None for index in guessed.values()) >= 2


# ── 重複判定 ──────────────────────────────────────────────────────────────

PREVIEW_HEADERS = ["取込", *HEADERS]


def _norm(value: str | None) -> str:
    """比較用に空白（半角・全角）を取り除いた文字列を返す。"""
    return (value or "").strip().replace(" ", "").replace("\u3000", "")


def _dup_keys(row) -> list[tuple]:
    """重複判定に使うキー。会員番号と「事業所名＋氏名」の両方で照合する。

    row は dict でも ProjectMember でも可。
    """
    if isinstance(row, dict):
        get = row.get
    else:
        get = lambda k, d="": getattr(row, k, d)  # noqa: E731
    keys: list[tuple] = []
    number = _norm(get("member_number", ""))
    if number:
        keys.append(("number", number))
    org = _norm(get("organization_name", ""))
    rep = _norm(get("representative_name", ""))
    if org or rep:
        keys.append(("name", org, rep))
    return keys


class RosterImportDialog(QDialog):
    """名簿への取り込みダイアログ。

    すでに登録済みの名簿がある場合も、その内容を残したまま行を追加する。
    （キャンセル等による後からの追加を想定）
    """

    def __init__(self, project_id: int, parent=None):
        super().__init__(parent)
        self._project_id = project_id
        self._existing_keys, self._existing_count = self._load_existing()
        self.setWindowTitle(
            "名簿に追加取り込み" if self._existing_count else "名簿の取り込み")
        self.resize(780, 600)
        self._raw_rows: list[list[str]] = []
        self._field_combos: dict[str, QComboBox] = {}
        self.added_count = 0
        self.skipped_count = 0
        self._build()

    def _load_existing(self) -> tuple[set, int]:
        """登録済み名簿の重複判定キーと件数を取得する。"""
        from app.services.project_service import get_project_members
        session = get_session()
        try:
            members = get_project_members(session, self._project_id)
            keys = set()
            for pm in members:
                keys.update(_dup_keys(pm))
            return keys, len(members)
        finally:
            session.close()

    def _build(self):
        layout = QVBoxLayout(self)

        if self._existing_count:
            notice = QLabel(
                f"現在の名簿：{self._existing_count} 件\n"
                "取り込んだデータは、いまの名簿を消さずに「追加」されます。")
            notice.setStyleSheet(
                "background: #EFF6FF; border: 1px solid #BFDBFE;"
                " border-radius: 4px; padding: 6px 10px; color: #1E3A8A;")
        else:
            notice = QLabel("この名簿はまだ空です。取り込んだデータが登録されます。")
            notice.setStyleSheet(
                "background: #F8FAFC; border: 1px solid #E2E8F0;"
                " border-radius: 4px; padding: 6px 10px; color: #475569;")
        layout.addWidget(notice)

        layout.addWidget(QLabel(
            "Excelからコピーして下の欄に貼り付けるか、Excelファイルを選択してください。\n"
            "読み込み後、各項目にどの列を当てるかを選べます（列順がバラバラでも可）。"
        ))

        self._paste_area = _TsvPasteEdit()
        self._paste_area.setPlaceholderText("ここにExcelの内容を貼り付け（Ctrl+V）")
        self._paste_area.setFixedHeight(90)
        layout.addWidget(self._paste_area)

        btn_row1 = QHBoxLayout()
        btn_parse = QPushButton("貼り付け内容を読み込む")
        btn_parse.clicked.connect(self._load_paste)
        btn_file = QPushButton("Excelファイルを選択")
        btn_file.clicked.connect(self._open_file)
        btn_row1.addWidget(btn_parse)
        btn_row1.addWidget(btn_file)
        btn_row1.addStretch()
        layout.addLayout(btn_row1)

        # ── 列の割り当て（マッピング）──────────────────────────
        self._map_group = QGroupBox("列の割り当て（取り込み先 ← 元の列）")
        map_layout = QGridLayout(self._map_group)
        self._header_chk = QCheckBox("1行目を見出しとして使う（見出し名から自動割り当て）")
        self._header_chk.stateChanged.connect(self._on_header_toggle)
        map_layout.addWidget(self._header_chk, 0, 0, 1, 4)

        for n, field in enumerate(ROSTER_COLUMNS):
            r = 1 + n // 2
            c = (n % 2) * 2
            label = FIELD_LABELS[field]
            if field in REQUIRED_ANY:
                label += " ※"
            combo = QComboBox()
            combo.currentIndexChanged.connect(self._refresh_preview)
            self._field_combos[field] = combo
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            map_layout.addWidget(lbl, r, c)
            map_layout.addWidget(combo, r, c + 1)

        map_layout.setColumnStretch(1, 1)
        map_layout.setColumnStretch(3, 1)

        note = QLabel("※「事業所名」「代表者名」のいずれかが必要です。")
        note.setStyleSheet("color: #666; font-size: 11px;")
        map_layout.addWidget(note, 1 + (len(ROSTER_COLUMNS) + 1) // 2, 0, 1, 4)
        self._map_group.setEnabled(False)
        layout.addWidget(self._map_group)

        # ── 重複の扱い ────────────────────────────────────────
        self._dup_chk = QCheckBox(
            "すでに名簿にある行は取り込まない"
            "（会員番号、または事業所名＋氏名で判定）")
        self._dup_chk.setChecked(self._existing_count > 0)
        self._dup_chk.stateChanged.connect(self._refresh_preview)
        layout.addWidget(self._dup_chk)

        # ── プレビュー ────────────────────────────────────────
        self._table = QTableWidget(0, len(PREVIEW_HEADERS))
        self._table.setHorizontalHeaderLabels(PREVIEW_HEADERS)
        prev_hdr = self._table.horizontalHeader()
        prev_hdr.setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        prev_hdr.setSectionResizeMode(
            1 + ROSTER_COLUMNS.index("organization_name"),
            QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        btn_row2 = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        self._btn_import = QPushButton(
            "名簿に追加する" if self._existing_count else "取り込み実行")
        self._btn_import.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; border-radius: 4px;"
            " font-weight: bold; padding: 2px 12px; }"
            "QPushButton:hover { background: #1D4ED8; }"
            "QPushButton:disabled { background: #94A3B8; color: white; }")
        self._btn_import.setEnabled(False)
        self._btn_import.clicked.connect(self._import)
        btn_row2.addWidget(btn_cancel)
        btn_row2.addStretch()
        btn_row2.addWidget(self._btn_import)
        layout.addLayout(btn_row2)

    # ── 読み込み ──────────────────────────────────────────────

    def _load_paste(self):
        rows = parse_tsv_text_raw(self._paste_area.toPlainText())
        if not rows:
            QMessageBox.warning(self, "読込エラー", "データが見つかりませんでした。")
            return
        self._set_raw_rows(rows)

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Excelファイルを選択", "", "Excel (*.xlsx *.xls)")
        if not path:
            return
        try:
            rows = parse_excel_file_raw(path)
        except Exception as e:
            QMessageBox.critical(self, "読込エラー", str(e))
            return
        if not rows:
            QMessageBox.warning(self, "読込エラー", "データが見つかりませんでした。")
            return
        self._set_raw_rows(rows)

    def _set_raw_rows(self, rows: list[list[str]]):
        self._raw_rows = rows
        self._header_chk.blockSignals(True)
        self._header_chk.setChecked(bool(rows) and _looks_like_header(rows[0]))
        self._header_chk.blockSignals(False)
        self._map_group.setEnabled(True)
        self._rebuild_mapping_ui()
        self._refresh_preview()

    # ── マッピングUI ──────────────────────────────────────────

    def _rebuild_mapping_ui(self):
        num_cols = column_count(self._raw_rows)
        sample = self._raw_rows[0] if self._raw_rows else []
        has_header = self._header_chk.isChecked()
        if has_header and self._raw_rows:
            guessed = _guess_mapping_from_header_roster(self._raw_rows[0])
        else:
            guessed = _default_positional_mapping_roster(num_cols)

        for field, combo in self._field_combos.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("（なし）", None)
            for i in range(num_cols):
                val = sample[i] if i < len(sample) else ""
                if len(val) > 12:
                    val = val[:12] + "…"
                combo.addItem(f"列{i + 1}: {val}", i)
            target = guessed.get(field)
            idx = combo.findData(target) if target is not None else 0
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

    def _on_header_toggle(self):
        if self._raw_rows:
            self._rebuild_mapping_ui()
            self._refresh_preview()

    def _current_mapping(self) -> dict[str, int | None]:
        return {field: combo.currentData()
                for field, combo in self._field_combos.items()}

    # ── プレビュー & 取り込み ─────────────────────────────────

    def _mapped_rows(self) -> list[dict]:
        return build_member_rows(
            self._raw_rows, self._current_mapping(),
            has_header=self._header_chk.isChecked())

    def _classify_rows(self) -> list[tuple[dict, bool]]:
        """(行, 既存または取り込み内で重複しているか) の一覧を返す。"""
        seen = set(self._existing_keys)
        result: list[tuple[dict, bool]] = []
        for row in self._mapped_rows():
            keys = _dup_keys(row)
            is_dup = any(k in seen for k in keys)
            seen.update(keys)
            result.append((row, is_dup))
        return result

    def _rows_to_import(self) -> tuple[list[dict], int]:
        """実際に登録する行と、重複でスキップする件数を返す。"""
        classified = self._classify_rows()
        if not self._dup_chk.isChecked():
            return [row for row, _ in classified], 0
        rows = [row for row, dup in classified if not dup]
        return rows, len(classified) - len(rows)

    def _refresh_preview(self):
        classified = self._classify_rows()
        skip_dup = self._dup_chk.isChecked()
        self._table.setRowCount(0)
        for row, is_dup in classified:
            r = self._table.rowCount()
            self._table.insertRow(r)
            if not is_dup:
                state, color = "追加", None
            elif skip_dup:
                state, color = "重複（スキップ）", QColor("#94A3B8")
            else:
                state, color = "重複（追加する）", QColor("#B45309")
            state_item = QTableWidgetItem(state)
            if color is not None:
                state_item.setForeground(color)
            self._table.setItem(r, 0, state_item)
            for c, col in enumerate(ROSTER_COLUMNS):
                item = QTableWidgetItem(row.get(col, ""))
                if color is not None:
                    item.setForeground(color)
                self._table.setItem(r, c + 1, item)
        rows, skipped = self._rows_to_import()
        text = f"取り込み対象：{len(rows)} 件"
        if skipped:
            text += f"（重複のためスキップ：{skipped} 件）"
        if self._existing_count:
            after = self._existing_count + len(rows)
            text += (f"　／　取り込み後の名簿："
                     f"{self._existing_count} 件 → {after} 件")
        self._status_label.setText(text)
        self._btn_import.setEnabled(len(rows) > 0)

    def _import(self):
        rows, skipped = self._rows_to_import()
        if not rows:
            QMessageBox.information(
                self, "取り込み対象なし",
                "追加できる行がありません。\n"
                "すべて既存の名簿と重複している可能性があります。")
            return

        if self._existing_count:
            confirm = (f"現在の名簿 {self._existing_count} 件に、"
                       f"{len(rows)} 件を追加します。\n"
                       "既存の行は削除されません。\n")
            if skipped:
                confirm += f"重複する {skipped} 件は取り込みません。\n"
            confirm += "\nよろしいですか？"
            if QMessageBox.question(
                    self, "名簿への追加", confirm
            ) != QMessageBox.StandardButton.Yes:
                return

        from app.services.project_service import add_roster_entries
        session = get_session()
        try:
            add_roster_entries(session, self._project_id, rows)
        except Exception as e:
            session.rollback()
            QMessageBox.critical(
                self, "インポートエラー",
                "名簿を登録できませんでした。\n"
                "列の割り当てと各項目の内容を確認してください。\n\n"
                f"{e}")
            return
        finally:
            session.close()

        self.added_count = len(rows)
        self.skipped_count = skipped
        msg = f"{len(rows)} 件を名簿に追加しました。\n"
        msg += (f"名簿の件数：{self._existing_count} 件 → "
                f"{self._existing_count + len(rows)} 件")
        if skipped:
            msg += f"\n\n重複のため取り込まなかった行：{skipped} 件"
        QMessageBox.information(self, "取り込み完了", msg)
        self.accept()
