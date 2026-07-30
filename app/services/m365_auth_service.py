# app/services/m365_auth_service.py
import msal
from pathlib import Path
from msal_extensions import PersistedTokenCache, build_encrypted_persistence

# Graph API への委任スコープ
_MAIL_SEND_SCOPE = "https://graph.microsoft.com/Mail.Send"
_MAIL_SEND_SHARED_SCOPE = "https://graph.microsoft.com/Mail.Send.Shared"

_CACHE_FILE = Path.home() / ".cci-billing" / "m365_token_cache.bin"


class M365AuthService:
    """MSAL認証。OAuthトークンはWindowsの暗号化機能付きで保存する。"""

    def __init__(self, client_id: str, tenant_id: str,
                 account_username: str | None = None,
                 include_shared: bool = False):
        if not client_id or not tenant_id:
            raise ValueError("M365 の client_id と tenant_id を設定してください。")
        _CACHE_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._remove_legacy_plaintext_cache()
        persistence = build_encrypted_persistence(str(_CACHE_FILE))
        self._cache = PersistedTokenCache(persistence)
        self._app = msal.PublicClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=self._cache,
        )
        if account_username is None:
            from app.utils.app_config import get_m365_account_username
            account_username = get_m365_account_username()
        self._account_username = (account_username or "").strip()
        self._scopes = [_MAIL_SEND_SCOPE]
        if include_shared:
            self._scopes.append(_MAIL_SEND_SHARED_SCOPE)

    @staticmethod
    def _remove_legacy_plaintext_cache() -> None:
        """旧版の平文トークンを残さず、暗号化キャッシュへ切り替える。"""
        if not _CACHE_FILE.exists():
            return
        try:
            is_plaintext = _CACHE_FILE.read_bytes().lstrip().startswith(b"{")
        except OSError:
            return
        if is_plaintext:
            _CACHE_FILE.unlink()

    def get_cached_accounts(self) -> list[str]:
        return sorted({
            account.get("username", "")
            for account in self._app.get_accounts()
            if account.get("username")
        })

    def acquire_token_with_account(
            self, force_interactive: bool = False) -> tuple[str, str]:
        """アクセストークンと実際に認証したアカウント名を返す。"""
        result = None
        accounts = self._app.get_accounts()
        selected_name = self._account_username.casefold()
        selected = next(
            (account for account in accounts
             if account.get("username", "").casefold() == selected_name),
            None,
        )
        if not selected and len(accounts) == 1:
            selected = accounts[0]
        if not selected and len(accounts) > 1 and not force_interactive:
            raise RuntimeError(
                "メール送信設定で送信に使用するMicrosoft 365アカウントを"
                "選択してください。")
        if selected and not force_interactive:
            result = self._app.acquire_token_silent(
                self._scopes, account=selected)

        if not result:
            result = self._app.acquire_token_interactive(scopes=self._scopes)

        if not result or "access_token" not in result:
            desc = result.get("error_description", str(result)) if result else "不明なエラー"
            raise RuntimeError(f"Microsoft 365 認証に失敗しました: {desc}")

        username = (
            result.get("id_token_claims", {}).get("preferred_username")
            or (selected or {}).get("username")
            or ""
        )
        return result["access_token"], username

    def acquire_token(self) -> str:
        return self.acquire_token_with_account()[0]

    def sign_out(self) -> None:
        for account in self._app.get_accounts():
            self._app.remove_account(account)
