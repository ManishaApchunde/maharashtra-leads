from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "mysql+pymysql://leads:leads@localhost:3306/maharashtra_leads?charset=utf8mb4"
    API_KEY: str = ""
    # Comma-separated list of Places API keys, tried in order when a key is rejected.
    GOOGLE_PLACES_API_KEYS: str = ""
    # Older single-key setting - still read, appended after GOOGLE_PLACES_API_KEYS.
    GOOGLE_PLACES_API_KEY: str = ""
    CORS_ORIGINS: str = "http://localhost:5173"
    OLD_RECORD_DAYS: int = 180

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def places_api_keys(self) -> list[str]:
        """All configured Places keys, in order, blanks and repeats removed. May be empty."""
        return parse_api_keys(self.GOOGLE_PLACES_API_KEYS, self.GOOGLE_PLACES_API_KEY)


def parse_api_keys(*values: str | None) -> list[str]:
    keys: list[str] = []
    for value in values:
        for part in (value or "").replace("\n", ",").split(","):
            k = part.strip().strip('"').strip("'").strip()
            if k and not k.startswith("#") and k not in keys:
                keys.append(k)
    return keys


@lru_cache
def get_settings() -> Settings:
    return Settings()
