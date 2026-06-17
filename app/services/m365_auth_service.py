# app/services/m365_auth_service.py
import msal

# Graph API への委任スコープ
_SCOPES = ["https://graph.microsoft.com/Mail.Send"]


class M365AuthService:
    """MSAL を使った Microsoft 365 対話型認証。"""

    def __init__(self, client_id: str, tenant_id: str):
        if not client_id or not tenant_id:
            raise ValueError("M365 の client_id と tenant_id を設定してください。")
        self._app = msal.PublicClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )

    def acquire_token(self) -> str:
        """アクセストークンを取得する。キャッシュがあればサイレント取得を優先する。"""
        result = None
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(_SCOPES, account=accounts[0])

        if not result:
            result = self._app.acquire_token_interactive(scopes=_SCOPES)

        if not result or "access_token" not in result:
            desc = result.get("error_description", str(result)) if result else "不明なエラー"
            raise RuntimeError(f"Microsoft 365 認証に失敗しました: {desc}")

        return result["access_token"]
