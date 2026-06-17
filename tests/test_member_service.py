# tests/test_member_service.py
"""会員マスタCSV取り込みのテスト。"""
from app.services.member_service import import_from_csv_with_mapping
from app.database.models import Member


def test_import_with_department_mapping_stores_department(db_session, tmp_path):
    csv_path = tmp_path / "members.csv"
    csv_path.write_text(
        "事業所名,所属・役職名\n○○商事,営業部 部長\n",
        encoding="utf-8",
    )
    mapping = {"事業所名": "organization_name", "所属・役職名": "department"}

    count = import_from_csv_with_mapping(db_session, str(csv_path), mapping)

    assert count == 1
    member = db_session.query(Member).one()
    assert member.department == "営業部 部長"
