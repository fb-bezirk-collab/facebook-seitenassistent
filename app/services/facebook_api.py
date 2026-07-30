from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from app.models.facebook_page import FacebookPage
from app.services.meta_config_service import MetaConfig


GRAPH_API_VERSION = "v25.0"
GRAPH_API_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
FACEBOOK_DIALOG_URL = f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth"


class FacebookApiError(Exception):
    pass


@dataclass
class FacebookToken:
    access_token: str
    token_type: str = ""
    expires_in: int | None = None


@dataclass
class FacebookUser:
    user_id: str
    name: str


class FacebookApiService:
    def __init__(self, config: MetaConfig):
        self.config = config

    def build_login_url(self, state: str) -> str:
        if not self.config.is_configured:
            raise FacebookApiError("Die Meta-App ist nicht vollständig konfiguriert.")

        parameters = {
            "client_id": self.config.app_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "state": state,
        }

        if self.config.config_id:
            parameters["config_id"] = self.config.config_id
        else:
            parameters["scope"] = ",".join(
                ["pages_show_list", "pages_read_engagement", "pages_manage_posts"]
            )

        return FACEBOOK_DIALOG_URL + "?" + urlencode(parameters)

    def exchange_code_for_token(self, code: str) -> FacebookToken:
        data = self._request_json(
            method="GET",
            url=GRAPH_API_BASE_URL + "/oauth/access_token",
            params={
                "client_id": self.config.app_id,
                "client_secret": self.config.app_secret,
                "redirect_uri": self.config.redirect_uri,
                "code": code,
            },
        )
        return self._token_from_response(data, "Meta hat kein Zugriffstoken zurückgegeben.")

    def exchange_for_long_lived_token(self, short_lived_token: str) -> FacebookToken:
        data = self._request_json(
            method="GET",
            url=GRAPH_API_BASE_URL + "/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self.config.app_id,
                "client_secret": self.config.app_secret,
                "fb_exchange_token": short_lived_token,
            },
        )
        return self._token_from_response(
            data,
            "Das länger gültige Zugriffstoken konnte nicht erzeugt werden.",
        )

    def get_user(self, user_access_token: str) -> FacebookUser:
        data = self._request_json(
            method="GET",
            url=GRAPH_API_BASE_URL + "/me",
            params={"access_token": user_access_token, "fields": "id,name"},
        )
        user_id = str(data.get("id", "")).strip()
        name = str(data.get("name", "")).strip()
        if not user_id or not name:
            raise FacebookApiError("Das verbundene Facebook-Konto konnte nicht gelesen werden.")
        return FacebookUser(user_id=user_id, name=name)

    def get_managed_pages(self, user_access_token: str) -> list[FacebookPage]:
        url = GRAPH_API_BASE_URL + "/me/accounts"
        parameters: dict | None = {
            "access_token": user_access_token,
            "fields": "id,name,access_token,tasks",
            "limit": 100,
        }
        pages: list[FacebookPage] = []

        while url:
            data = self._request_json(method="GET", url=url, params=parameters)
            for item in data.get("data", []):
                if not isinstance(item, dict):
                    continue
                page_id = str(item.get("id", "")).strip()
                page_name = str(item.get("name", "")).strip()
                page_access_token = str(item.get("access_token", "")).strip()
                if not (page_id and page_name and page_access_token):
                    continue
                pages.append(
                    FacebookPage(
                        page_id=page_id,
                        name=page_name,
                        access_token=page_access_token,
                        is_default=False,
                        is_active=True,
                    )
                )

            paging = data.get("paging", {})
            next_url = paging.get("next") if isinstance(paging, dict) else None
            if not next_url:
                break
            url = str(next_url)
            parameters = None

        return pages

    @staticmethod
    def _token_from_response(data: dict, message: str) -> FacebookToken:
        access_token = str(data.get("access_token", "")).strip()
        if not access_token:
            raise FacebookApiError(message)
        return FacebookToken(
            access_token=access_token,
            token_type=str(data.get("token_type", "")),
            expires_in=FacebookApiService._to_int_or_none(data.get("expires_in")),
        )

    @staticmethod
    def _request_json(method: str, url: str, params: dict | None = None) -> dict:
        try:
            response = requests.request(method=method, url=url, params=params, timeout=30)
        except requests.RequestException as error:
            raise FacebookApiError(f"Facebook konnte nicht erreicht werden: {error}") from error

        try:
            data = response.json()
        except ValueError as error:
            raise FacebookApiError("Facebook hat keine gültige Antwort zurückgegeben.") from error

        if response.ok:
            return data

        error_data = data.get("error", {})
        if isinstance(error_data, dict):
            message = error_data.get("message", "Unbekannter Facebook-Fehler")
        else:
            message = str(error_data)
        raise FacebookApiError(str(message))

    @staticmethod
    def _to_int_or_none(value) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
