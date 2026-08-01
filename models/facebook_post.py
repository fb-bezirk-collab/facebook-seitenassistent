from dataclasses import dataclass, field


@dataclass
class FacebookPost:
    text: str
    images: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    video_url: str = ""
    source_url: str = ""
