# app/services/member_service.py
import csv
import io
from sqlalchemy.orm import Session
from app.database.models import Member

_COLUMN_ALIASES = {
    "member_number":       ["会員番号", "会員no", "会員ｎｏ", "memberid", "member_id"],
    "organization_name":   ["事業所名", "会社名", "法人名", "organization"],
    "organization_kana":   ["フリガナ", "事業所フリガナ", "フリガナ（事業所）", "kana"],
    "representative_name": ["氏名", "代表者名", "担当者名", "name"],
    "representative_kana": ["氏名フリガナ", "代表者フリガナ", "氏名かな"],
    "department":          ["所属", "役職", "所属役職", "所属・役職", "部署", "役職名"],
    "phone":               ["電話番号", "tel", "電話", "phone"],
    "email":               ["メール", "メールアドレス", "mail", "e-mail"],
    "postal_code":         ["郵便番号", "zip", "zipcode"],
    "address":             ["住所", "住所1", "住所１", "address1"],
    "address2":            ["住所2", "住所２", "建物名", "番地以下"],
}

_MEMBER_FIELDS = set(_COLUMN_ALIASES.keys())

# DBに持たない仮想フィールド（インポート時に合成処理を行う）
_VIRTUAL_ALIASES: dict[str, list[str]] = {
    "phone_area": ["電話市外局番", "市外局番", "電話（市外局番）", "電話市外"],
}

# UI表示用ラベル（仮想フィールドを含む）
_FIELD_LABELS: dict[str, str] = {
    "member_number":       "会員番号",
    "organization_name":   "事業所名",
    "organization_kana":   "フリガナ（事業所）",
    "representative_name": "氏名",
    "representative_kana": "氏名フリガナ",
    "department":          "所属・役職名",
    "phone_area":          "電話（市外局番）",
    "phone":               "電話番号（市番）",
    "email":               "メール",
    "postal_code":         "郵便番号",
    "address":             "住所",
    "address2":            "住所2",
}

# 小文字マップ: lowercase alias → field name
_LOWER_MAP: dict[str, str] = {}
for _field, _aliases in _COLUMN_ALIASES.items():
    _LOWER_MAP[_field.lower()] = _field
    for _a in _aliases:
        _LOWER_MAP[_a.lower()] = _field
for _field, _aliases in _VIRTUAL_ALIASES.items():
    _LOWER_MAP[_field.lower()] = _field
    for _a in _aliases:
        _LOWER_MAP[_a.lower()] = _field


def _strip_excel_formula(val: str) -> str:
    """="059" や ='059' のようなExcel式文字列から値だけを取り出す。"""
    s = val.strip()
    if len(s) >= 3 and s[0] == "=" and s[1] in ('"', "'") and s[-1] == s[1]:
        return s[2:-1]
    return s


def _read_csv_text(file_path: str) -> str:
    raw = open(file_path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_csv_headers_and_preview(file_path: str, max_preview: int = 3) -> tuple[list[str], list[dict]]:
    """CSVのヘッダーと先頭数行のプレビューを返す。"""
    text = _read_csv_text(file_path)
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    preview = []
    for i, row in enumerate(reader):
        if i >= max_preview:
            break
        preview.append({k: _strip_excel_formula(v or "") for k, v in row.items()})
    return headers, preview


def detect_mapping(headers: list[str]) -> dict[str, str]:
    """ヘッダーリストから自動検出したマッピング {csv_header: field_name} を返す。"""
    return {hdr: field
            for hdr in headers
            if (field := _LOWER_MAP.get(hdr.strip().lower()))}


def import_from_csv_with_mapping(session: Session, file_path: str, mapping: dict[str, str]) -> int:
    """明示的なマッピングでCSVから会員マスタを一括登録（既存全削除→再登録）。"""
    text = _read_csv_text(file_path)
    reader = csv.DictReader(io.StringIO(text))

    session.query(Member).delete()
    session.flush()

    count = 0
    for row in reader:
        data: dict[str, str] = {}
        for hdr, field in mapping.items():
            if field:
                data[field] = _strip_excel_formula((row.get(hdr) or "").strip())

        # 市外局番と市番を結合して phone フィールドに格納
        area = data.pop("phone_area", "")
        local = data.get("phone", "")
        if area:
            if local:
                sep = "" if area.endswith("-") or local.startswith("-") else "-"
                data["phone"] = area + sep + local
            else:
                data["phone"] = area

        if not data.get("organization_name") and not data.get("member_number"):
            continue
        kwargs = {k: v for k, v in data.items() if k in _MEMBER_FIELDS}
        session.add(Member(**kwargs))
        count += 1

    session.commit()
    return count


def import_from_csv(session: Session, file_path: str) -> int:
    """CSVから会員マスタを一括登録（自動マッピング）。既存データ全削除→再登録。"""
    text = _read_csv_text(file_path)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return 0

    col_map: dict[str, str] = {
        hdr: field
        for hdr in reader.fieldnames
        if (field := _LOWER_MAP.get(hdr.strip().lower()))
    }
    return import_from_csv_with_mapping(session, file_path, col_map)


def get_all_members(session: Session) -> list:
    return session.query(Member).order_by(Member.organization_name).all()


def search_members(session: Session, query: str, limit: int = 50) -> list:
    q = (query or "").strip()
    if not q:
        return []
    from sqlalchemy import or_
    return (session.query(Member)
            .filter(or_(
                Member.organization_name.contains(q),
                Member.organization_kana.contains(q),
                Member.member_number.contains(q),
            ))
            .limit(limit)
            .all())


def count_members(session: Session) -> int:
    return session.query(Member).count()
