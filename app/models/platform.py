from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformDefinition:
    id: str
    name: str
    account_label: str
    external_id_label: str
    color: str
    connection_mode: str
    can_publish: bool
    can_connect: bool
    description: str


PLATFORM_DEFINITIONS: tuple[PlatformDefinition, ...] = (
    PlatformDefinition(
        id="facebook",
        name="Facebook",
        account_label="Facebook-Seite",
        external_id_label="Seiten-ID",
        color="#1877f2",
        connection_mode="meta",
        can_publish=True,
        can_connect=True,
        description=(
            "Facebook-Seiten werden über die bestehende "
            "Meta-Verbindung automatisch übernommen."
        ),
    ),
    PlatformDefinition(
        id="instagram",
        name="Instagram",
        account_label="Instagram-Konto",
        external_id_label="Instagram-Konto-ID",
        color="#c13584",
        connection_mode="meta",
        can_publish=False,
        can_connect=False,
        description=(
            "Instagram-Business- und Creator-Konten werden über "
            "dieselbe Meta-Verbindung automatisch übernommen."
        ),
    ),
    PlatformDefinition(
        id="x",
        name="X",
        account_label="X-Konto",
        external_id_label="Konto-ID",
        color="#111111",
        connection_mode="separate",
        can_publish=False,
        can_connect=False,
        description=(
            "Für X wird später eine eigene API-Verbindung benötigt."
        ),
    ),
    PlatformDefinition(
        id="tiktok",
        name="TikTok",
        account_label="TikTok-Konto",
        external_id_label="Konto-ID",
        color="#111111",
        connection_mode="separate",
        can_publish=False,
        can_connect=False,
        description=(
            "TikTok wird später als eigene Plattform ergänzt."
        ),
    ),
)


PLATFORM_BY_ID = {
    platform.id: platform
    for platform in PLATFORM_DEFINITIONS
}


def get_platform(platform_id: str) -> PlatformDefinition | None:
    return PLATFORM_BY_ID.get(platform_id.strip().lower())
