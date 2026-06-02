import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(PROJECT_ROOT / ".env"),
            str(PROJECT_ROOT / "backend" / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./rakshak.db"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "rakshak_dev_password"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    ocr_languages: str = "eng+kan"
    ocr_dpi: int = 300

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_label(self) -> str:
        url = self.database_url
        if url.startswith("sqlite"):
            return url
        if "@" in url:
            return url.split("@", 1)[1]
        return url


settings = Settings()
