from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from app.models.facebook_page import FacebookPage
from app.models.instagram_account import InstagramAccount
from app.services.meta_config_service import MetaConfig


GRAPH_API_VERSION = "v25.0"
GRAPH_API_BASE_URL = (
    f"https://graph.facebook.com/{GRAPH_API_VERSION}"
)

FACEBOOK_DIALOG_URL = (
    f"https://www.facebook.com/{GRAPH_API_VERSION}"
    "/dialog/oauth"
)

REQUIRED_PAGE_PERMISSIONS = (
    "pages_show_list",
    "business_management",
    "pages_read_engagement",
    "pages_manage_posts",
    "pages_read_user_content",
    "pages_manage_engagement",
)


class FacebookApiError(Exception):
    pass


@dataclass
class FacebookToken:
    access_token: str
    token_type: str = ""
    expires_in: int | None = None


class FacebookApiService:
    def __init__(
        self,
        config: MetaConfig,
    ):
        self.config = config

    def build_login_url(
        self,
        state: str,
    ) -> str:
        if not self.config.is_configured:
            raise FacebookApiError(
                "Die Meta-App ist nicht vollständig "
                "konfiguriert."
            )

        parameters = {
            "client_id": self.config.app_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "config_id": self.config.config_id,
            "state": state,
        }

        return (
            FACEBOOK_DIALOG_URL
            + "?"
            + urlencode(parameters)
        )

    def exchange_code_for_token(
        self,
        code: str,
    ) -> FacebookToken:
        url = (
            GRAPH_API_BASE_URL
            + "/oauth/access_token"
        )

        parameters = {
            "client_id": self.config.app_id,
            "client_secret": self.config.app_secret,
            "redirect_uri": self.config.redirect_uri,
            "code": code,
        }

        data = self._request_json(
            method="GET",
            url=url,
            params=parameters,
        )

        access_token = str(
            data.get("access_token", "")
        ).strip()

        if not access_token:
            raise FacebookApiError(
                "Meta hat kein Zugriffstoken "
                "zurückgegeben."
            )

        return FacebookToken(
            access_token=access_token,
            token_type=str(
                data.get("token_type", "")
            ),
            expires_in=self._to_int_or_none(
                data.get("expires_in")
            ),
        )

    def exchange_for_long_lived_token(
        self,
        short_lived_token: str,
    ) -> FacebookToken:
        url = (
            GRAPH_API_BASE_URL
            + "/oauth/access_token"
        )

        parameters = {
            "grant_type": "fb_exchange_token",
            "client_id": self.config.app_id,
            "client_secret": self.config.app_secret,
            "fb_exchange_token": short_lived_token,
        }

        data = self._request_json(
            method="GET",
            url=url,
            params=parameters,
        )

        access_token = str(
            data.get("access_token", "")
        ).strip()

        if not access_token:
            raise FacebookApiError(
                "Das länger gültige Zugriffstoken "
                "konnte nicht erzeugt werden."
            )

        return FacebookToken(
            access_token=access_token,
            token_type=str(
                data.get("token_type", "")
            ),
            expires_in=self._to_int_or_none(
                data.get("expires_in")
            ),
        )

    def get_user_permissions(
        self,
        user_access_token: str,
    ) -> dict[str, str]:
        """Liest die tatsächlich am User-Token gewährten Facebook-Rechte."""
        url = GRAPH_API_BASE_URL + "/me/permissions"
        data = self._request_json(
            method="GET",
            url=url,
            params={
                "access_token": user_access_token,
                "limit": 100,
            },
        )

        permissions: dict[str, str] = {}
        for item in data.get("data", []):
            if not isinstance(item, dict):
                continue
            permission = str(item.get("permission", "")).strip()
            status = str(item.get("status", "")).strip().lower()
            if permission:
                permissions[permission] = status
        return permissions

    def missing_required_page_permissions(
        self,
        user_access_token: str,
    ) -> list[str]:
        granted = self.get_user_permissions(user_access_token)
        return [
            permission
            for permission in REQUIRED_PAGE_PERMISSIONS
            if granted.get(permission) != "granted"
        ]

    def get_managed_pages(
        self,
        user_access_token: str,
    ) -> list[FacebookPage]:
        url = GRAPH_API_BASE_URL + "/me/accounts"

        parameters = {
            "access_token": user_access_token,
            "fields": (
                "id,name,access_token,tasks"
            ),
            "limit": 100,
        }

        pages: list[FacebookPage] = []

        while url:
            data = self._request_json(
                method="GET",
                url=url,
                params=parameters,
            )

            for item in data.get("data", []):
                if not isinstance(item, dict):
                    continue

                page_id = str(
                    item.get("id", "")
                ).strip()

                page_name = str(
                    item.get("name", "")
                ).strip()

                page_access_token = str(
                    item.get("access_token", "")
                ).strip()

                if not (
                    page_id
                    and page_name
                    and page_access_token
                ):
                    continue

                pages.append(
                    FacebookPage(
                        page_id=page_id,
                        name=page_name,
                        access_token=(
                            page_access_token
                        ),
                        is_default=False,
                        is_active=True,
                    )
                )

            paging = data.get("paging", {})

            if not isinstance(paging, dict):
                break

            next_url = paging.get("next")

            if not next_url:
                break

            url = str(next_url)
            parameters = None

        return pages

    def get_instagram_accounts(
        self,
        pages: list[FacebookPage],
    ) -> tuple[list[InstagramAccount], list[str]]:
        """Lädt Instagram-Business-/Creator-Konten, die mit Seiten verbunden sind."""
        accounts: list[InstagramAccount] = []
        warnings: list[str] = []
        known_ids: set[str] = set()

        for page in pages:
            url = GRAPH_API_BASE_URL + f"/{page.page_id}"
            parameters = {
                "access_token": page.access_token,
                "fields": (
                    "instagram_business_account"
                    "{id,username,name,profile_picture_url}"
                ),
            }

            try:
                data = self._request_json(
                    method="GET",
                    url=url,
                    params=parameters,
                )
            except FacebookApiError as error:
                warnings.append(
                    f"Instagram konnte für {page.name} nicht geprüft werden: {error}"
                )
                continue

            instagram = data.get("instagram_business_account")
            if not isinstance(instagram, dict):
                continue

            instagram_id = str(instagram.get("id", "")).strip()
            if not instagram_id or instagram_id in known_ids:
                continue

            username = str(instagram.get("username", "")).strip()
            name = str(instagram.get("name", "")).strip()
            profile_picture_url = str(
                instagram.get("profile_picture_url", "")
            ).strip()

            accounts.append(
                InstagramAccount(
                    instagram_id=instagram_id,
                    username=username,
                    name=name,
                    profile_picture_url=profile_picture_url,
                    connected_page_id=page.page_id,
                    connected_page_name=page.name,
                )
            )
            known_ids.add(instagram_id)

        return accounts, warnings

    def get_page_published_posts(
        self,
        page_id: str,
        page_access_token: str,
        limit: int = 25,
    ) -> list[dict]:
        url = GRAPH_API_BASE_URL + f"/{page_id}/published_posts"
        params = {
            "access_token": page_access_token,
            "fields": "id,message,created_time,permalink_url",
            "limit": max(1, min(int(limit), 100)),
        }
        return self._read_edge(url=url, params=params, max_items=max(1, min(int(limit), 100)))

    def get_post_comments(
        self,
        post_id: str,
        page_access_token: str,
        limit: int = 100,
    ) -> list[dict]:
        url = GRAPH_API_BASE_URL + f"/{post_id}/comments"
        params = {
            "access_token": page_access_token,
            "fields": (
                "id,message,created_time,from{id,name},permalink_url,"
                "is_hidden,can_hide,can_remove,parent{id}"
            ),
            "filter": "stream",
            "order": "reverse_chronological",
            "limit": min(max(1, int(limit)), 100),
        }
        return self._read_edge(url=url, params=params, max_items=max(1, int(limit)))

    def set_comment_hidden(
        self,
        comment_id: str,
        page_access_token: str,
        hidden: bool = True,
    ) -> None:
        url = GRAPH_API_BASE_URL + f"/{comment_id}"
        data = self._request_json(
            method="POST",
            url=url,
            params={
                "access_token": page_access_token,
                "is_hidden": "true" if hidden else "false",
            },
        )
        if data is False or (isinstance(data, dict) and data.get("success") is False):
            raise FacebookApiError("Facebook konnte den Kommentarstatus nicht ändern.")

    def set_page_user_blocked(
        self,
        page_id: str,
        page_access_token: str,
        user_id: str,
        blocked: bool = True,
    ) -> None:
        """Blockiert/entsperrt eine Page-Scoped User-ID auf einer Facebook-Seite."""
        if not user_id:
            raise FacebookApiError("Für diesen Benutzer ist keine Facebook-ID verfügbar.")
        url = GRAPH_API_BASE_URL + f"/{page_id}/blocked"
        method = "POST" if blocked else "DELETE"
        data = self._request_json(
            method=method,
            url=url,
            params={
                "access_token": page_access_token,
                "user": user_id,
            },
        )
        if data is False or (isinstance(data, dict) and data.get("success") is False):
            action = "sperren" if blocked else "entsperren"
            raise FacebookApiError(f"Facebook konnte den Benutzer nicht {action}.")

    def delete_comment(
        self,
        comment_id: str,
        page_access_token: str,
    ) -> None:
        url = GRAPH_API_BASE_URL + f"/{comment_id}"
        data = self._request_json(
            method="DELETE",
            url=url,
            params={"access_token": page_access_token},
        )
        if data is False or (isinstance(data, dict) and data.get("success") is False):
            raise FacebookApiError("Facebook konnte den Kommentar nicht löschen.")

    def _read_edge(
        self,
        url: str,
        params: dict | None,
        max_items: int,
    ) -> list[dict]:
        items: list[dict] = []
        next_url: str | None = url
        next_params = params

        while next_url and len(items) < max_items:
            data = self._request_json(
                method="GET",
                url=next_url,
                params=next_params,
            )
            for item in data.get("data", []):
                if isinstance(item, dict):
                    items.append(item)
                    if len(items) >= max_items:
                        break

            paging = data.get("paging")
            if not isinstance(paging, dict):
                break
            raw_next = paging.get("next")
            if not raw_next:
                break
            next_url = str(raw_next)
            next_params = None

        return items

    @staticmethod
    def _request_json(
        method: str,
        url: str,
        params: dict | None = None,
    ) -> dict:
        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                timeout=30,
            )

        except requests.RequestException as error:
            raise FacebookApiError(
                "Facebook konnte nicht erreicht werden: "
                f"{error}"
            ) from error

        try:
            data = response.json()

        except ValueError as error:
            raise FacebookApiError(
                "Facebook hat keine gültige "
                "Antwort zurückgegeben."
            ) from error

        if response.ok:
            return data

        error_data = data.get("error", {})

        if isinstance(error_data, dict):
            message = str(error_data.get("message", "Unbekannter Facebook-Fehler"))
            details = []
            code = error_data.get("code")
            error_type = error_data.get("type")
            subcode = error_data.get("error_subcode")
            trace_id = error_data.get("fbtrace_id")
            if code is not None:
                details.append(f"Code {code}")
            if error_type:
                details.append(str(error_type))
            if subcode is not None:
                details.append(f"Subcode {subcode}")
            if trace_id:
                details.append(f"Trace {trace_id}")
            if details:
                message += " [" + " · ".join(details) + "]"
        else:
            message = str(error_data)

        raise FacebookApiError(message)

    @staticmethod
    def _to_int_or_none(
        value,
    ) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None