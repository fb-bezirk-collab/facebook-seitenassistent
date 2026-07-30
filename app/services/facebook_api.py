from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from app.models.facebook_page import FacebookPage
from app.services.meta_config_service import MetaConfig


GRAPH_API_VERSION = "v25.0"
GRAPH_API_BASE_URL = (
    f"https://graph.facebook.com/{GRAPH_API_VERSION}"
)

FACEBOOK_DIALOG_URL = (
    f"https://www.facebook.com/{GRAPH_API_VERSION}"
    "/dialog/oauth"
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
            message = error_data.get(
                "message",
                "Unbekannter Facebook-Fehler",
            )
        else:
            message = str(error_data)

        raise FacebookApiError(str(message))

    @staticmethod
    def _to_int_or_none(
        value,
    ) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None