"""Application configuration settings."""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application configuration."""

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # File management
    DOWNLOAD_DIR: str = "/app/downloads"
    MAX_FILE_AGE_SECONDS: int = 3600  # 1 hour
    CLEANUP_INTERVAL_SECONDS: int = 300  # 5 minutes
    POST_SERVE_DELETE_DELAY: int = 60  # 1 minute

    # Download limits
    MAX_FILE_SIZE_MB: int = 500
    DOWNLOAD_TIMEOUT_SECONDS: int = 300  # 5 minutes

    # yt-dlp updates
    YTDLP_UPDATE_CHECK_INTERVAL: int = 600  # 10 minutes

    # Security
    MAX_URL_LENGTH: int = 2000
    ALLOWED_DOMAINS: List[str] = [
        "youtube.com", "youtu.be",
        "facebook.com", "fb.watch",
        "instagram.com",
        "twitter.com", "x.com",
        "vimeo.com"
    ]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
