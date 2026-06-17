# tests/test_roster_recipient.py
from app.database.models import ProjectMember
from app.services.roster_recipient import recipient_label


def test_recipient_label_org_and_rep():
    pm = ProjectMember(organization_name="○○商事", representative_name="田中太郎")
    assert recipient_label(pm) == "○○商事 田中太郎 様"


def test_recipient_label_org_only():
    pm = ProjectMember(organization_name="○○商事", representative_name="")
    assert recipient_label(pm) == "○○商事 御中"


def test_recipient_label_rep_only():
    pm = ProjectMember(organization_name="", representative_name="田中太郎")
    assert recipient_label(pm) == "田中太郎 様"
