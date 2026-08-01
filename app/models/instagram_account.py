from dataclasses import asdict, dataclass


@dataclass
class InstagramAccount:
    instagram_id: str
    username: str
    name: str = ""
    profile_picture_url: str = ""
    connected_page_id: str = ""
    connected_page_name: str = ""

    @property
    def display_name(self) -> str:
        return self.name.strip() or self.username.strip() or self.instagram_id

    def to_dict(self) -> dict:
        return asdict(self)
