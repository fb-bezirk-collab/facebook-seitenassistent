from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests


_URL_RE = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        data = {str(k).lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (data.get("property") or data.get("name") or "").strip().lower()
            content = data.get("content", "").strip()
            if key and content and key not in self.meta:
                self.meta[key] = content
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            text = data.strip()
            if text:
                self.title_parts.append(text)


def first_http_url(text: str) -> str:
    if not text:
        return ""
    match = _URL_RE.search(text)
    if not match:
        return ""
    return match.group(0).rstrip(".,;:!?)]}")


def _is_public_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError:
        return False
    addresses = {item[4][0] for item in infos if item and item[4]}
    if not addresses:
        return False
    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw.split("%", 1)[0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def fetch_link_preview(url: str, timeout: int = 8) -> dict[str, str]:
    """Liest eine kleine OpenGraph-Vorschau für einen öffentlichen Kommentar-Link.

    Die Funktion folgt höchstens wenigen Redirects und verweigert private/lokale Ziele,
    damit ein Nutzerkommentar nicht für Server-Side-Requests ins interne Netz missbraucht
    werden kann.
    """
    if not url or not _is_public_http_url(url):
        return {}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; FacebookSeitenassistent/2.8.3; "
            "+https://facebook.com/)"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
    except requests.RequestException:
        return {}

    try:
        final_url = response.url
        if not response.ok or not _is_public_http_url(final_url):
            return {}
        content_type = (response.headers.get("content-type") or "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return {}
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(chunk_size=16384):
            if not chunk:
                continue
            chunks.append(chunk)
            size += len(chunk)
            if size >= 512_000:
                break
        html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    finally:
        response.close()

    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:
        return {}

    image = (
        parser.meta.get("og:image:secure_url")
        or parser.meta.get("og:image")
        or parser.meta.get("twitter:image")
        or parser.meta.get("twitter:image:src")
        or ""
    ).strip()
    title = (
        parser.meta.get("og:title")
        or parser.meta.get("twitter:title")
        or " ".join(parser.title_parts)
        or ""
    ).strip()
    description = (
        parser.meta.get("og:description")
        or parser.meta.get("twitter:description")
        or parser.meta.get("description")
        or ""
    ).strip()

    if image:
        image = urljoin(final_url, image)
        if not _is_public_http_url(image):
            image = ""

    return {
        "url": final_url,
        "image_url": image,
        "title": title[:500],
        "description": description[:1000],
    }
