# app/services/roster_recipient.py
from app.database.models import ProjectMember


def recipient_label(pm: ProjectMember) -> str:
    if pm.organization_name and pm.representative_name:
        return f"{pm.organization_name} {pm.representative_name} 様"
    if pm.organization_name:
        return f"{pm.organization_name} 御中"
    return f"{pm.representative_name} 様"
