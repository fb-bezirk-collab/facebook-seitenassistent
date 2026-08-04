from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from app.models.instagram_connection import InstagramConnection
from app.services.instagram_config_service import InstagramConfig


class InstagramApiError(RuntimeError):
    pass


class InstagramApiService:
    api_version = "v23.0"

    def __init__(self, config: InstagramConfig):
        self.config = config

    def build_login_url(self, state: str) -> str:
        if not self.config.is_configured:
            raise InstagramApiError("Instagram-App ist nicht vollständig konfiguriert.")
        query = urlencode({
            "client_id": self.config.app_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": ",".join([
                "instagram_business_basic",
                "instagram_business_content_publish",
            ]),
            "state": state,
            "enable_fb_login": "0",
            "force_authentication": "1",
        })
        return "https://www.instagram.com/oauth/authorize?" + query

    def exchange_code(self, code: str) -> str:
        try:
            response = requests.post(
                "https://api.instagram.com/oauth/access_token",
                data={
                    "client_id": self.config.app_id,
                    "client_secret": self.config.app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.config.redirect_uri,
                    "code": code,
                },
                timeout=45,
            )
        except requests.RequestException as exc:
            raise InstagramApiError(f"Instagram ist nicht erreichbar: {exc}") from exc
        data = self._json(response)
        token = str(data.get("access_token", "")).strip()
        if not token:
            raise InstagramApiError("Instagram hat keinen Zugriffstoken geliefert.")
        return token

    def exchange_long_lived(self, short_token: str) -> tuple[str, str]:
        try:
            response = requests.get(
                "https://graph.instagram.com/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": self.config.app_secret,
                    "access_token": short_token,
                },
                timeout=45,
            )
        except requests.RequestException as exc:
            raise InstagramApiError(f"Langzeittoken konnte nicht geladen werden: {exc}") from exc
        data = self._json(response)
        token = str(data.get("access_token", "")).strip() or short_token
        expires_in = int(data.get("expires_in", 0) or 0)
        expires_at = ""
        if expires_in:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            ).isoformat(timespec="seconds")
        return token, expires_at

    def get_profile(self, access_token: str, expires_at: str = "") -> InstagramConnection:
        response = requests.get(
            f"https://graph.instagram.com/{self.api_version}/me",
            params={
                "fields": "user_id,username,name,profile_picture_url",
                "access_token": access_token,
            },
            timeout=45,
        )
        data = self._json(response)

        print(
            "INSTAGRAM_PROFILE_RESPONSE|"
            f"id={data.get('id')}|"
            f"user_id={data.get('user_id')}|"
            f"username={data.get('username')}|"
            f"name={data.get('name')}",
            flush=True,
        )

        instagram_id = str(
            data.get("id")
            or data.get("user_id")
            or ""
        ).strip()
        if not instagram_id:
            raise InstagramApiError("Instagram-Konto-ID konnte nicht gelesen werden.")
        return InstagramConnection(
            instagram_id=instagram_id,
            username=str(data.get("username", "")).strip(),
            name=str(data.get("name", "")).strip(),
            profile_picture_url=str(data.get("profile_picture_url", "")).strip(),
            access_token=access_token,
            token_expires_at=expires_at,
        )

    @staticmethod
    def _json(response: requests.Response) -> dict:
        try:
            data = response.json()
        except ValueError as exc:
            raise InstagramApiError("Instagram hat keine gültige Antwort geliefert.") from exc
        if response.status_code >= 400:
            error = data.get("error", {})
            message = error.get("message") if isinstance(error, dict) else None
            raise InstagramApiError(str(message or response.text or response.status_code))
        return data
