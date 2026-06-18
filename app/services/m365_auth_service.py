# app/services/m365_auth_service.py
import msal
from pathlib import Path

# Graph API への委任スコープ
_SCOPES = ["https://graph.microsoft.com/Mail.Send"]

_CACHE_FILE = Path.home() / ".cci-billing" / "m365_token_cache.bin"


class M365AuthService:
    """MSAL を使った Microsoft 365 対話型認証。"""

    def __init__(self, client_id: str, tenant_id: str):
        if not client_id or not tenant_id:
            raise ValueError("M365 の client_id と tenant_id を設定してください。")
        self._cache = msal.SerializableTokenCache()
        if _CACHE_FILE.exists():
            self._cache.deserialize(_CACHE_FILE.read_text(encoding="utf-8"))
        self._app = msal.PublicClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=self._cache,
        )

    def _save_cache(self):
        if self._cache.has_state_changed:
            import os
            _CACHE_FILE.parent.mkdir(mode=0o700, exist_ok=True)
            try:
                os.chmod(_CACHE_FILE.parent, 0o700)
            except OSError:
                pass
            fd = os.open(str(_CACHE_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(self._cache.serialize())

    def acquire_token(self) -> str:
        """アクセストークンを取得する。キャッシュがあればサイレント取得を優先する。"""
        result = None
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(_SCOPES, account=accounts[0])

        if not result:
            result = self._app.acquire_token_interactive(scopes=_SCOPES)

        self._save_cache()

        if not result or "access_token" not in result:
            desc = result.get("error_description", str(result)) if result else "不明なエラー"
            raise RuntimeError(f"Microsoft 365 認証に失敗しました: {desc}")

        return result["access_token"]
