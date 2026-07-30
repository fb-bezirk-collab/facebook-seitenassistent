import json
from pathlib import Path
from uuid import uuid4

from app.config import SOCIAL_ACCOUNTS_FILE
from app.models.social_account import SocialAccount
from app.services.settings_service import SettingsService


class SocialAccountService:
    def __init__(self, file_path: Path = SOCIAL_ACCOUNTS_FILE):
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists(): self._save_all([])

    def list_accounts(self, include_inactive: bool = True) -> list[SocialAccount]:
        accounts = self._load_all()
        accounts = self._merge_facebook_pages(accounts)
        if not include_inactive: accounts = [a for a in accounts if a.active]
        return sorted(accounts, key=lambda a: (a.platform, a.name.lower()))

    def get(self, account_id: str) -> SocialAccount | None:
        return next((a for a in self.list_accounts() if a.id == account_id), None)

    def create(self, *, platform: str, name: str, external_id: str = "") -> SocialAccount:
        account = SocialAccount(id=str(uuid4()), platform=platform, name=name, external_id=external_id)
        accounts=self._load_all(); accounts.append(account); self._save_all(accounts); return account

    def toggle(self, account_id: str) -> bool:
        accounts=self._load_all()
        for account in accounts:
            if account.id == account_id:
                account.active = not account.active; self._save_all(accounts); return True
        return False

    def delete(self, account_id: str) -> bool:
        accounts=self._load_all(); remaining=[a for a in accounts if a.id != account_id]
        if len(remaining)==len(accounts): return False
        self._save_all(remaining); return True

    def _merge_facebook_pages(self, accounts: list[SocialAccount]) -> list[SocialAccount]:
        known={(a.platform,a.external_id) for a in accounts if a.external_id}
        changed=False
        for page in SettingsService().load_pages():
            key=("facebook", page.page_id)
            if key in known: continue
            accounts.append(SocialAccount(id=f"facebook:{page.page_id}", platform="facebook", name=page.name, external_id=page.page_id, connection_status="connected"))
            known.add(key); changed=True
        # connected Facebook pages are dynamically merged; not written to avoid duplicating token-backed data
        return accounts

    def _load_all(self) -> list[SocialAccount]:
        try: raw=json.loads(self.file_path.read_text(encoding='utf-8') or '[]')
        except (OSError, json.JSONDecodeError): return []
        return [SocialAccount.from_dict(x) for x in raw if isinstance(x,dict) and x.get('id') and x.get('name')]

    def _save_all(self, accounts: list[SocialAccount]) -> None:
        self.file_path.write_text(json.dumps([a.to_dict() for a in accounts], ensure_ascii=False, indent=4), encoding='utf-8')
