# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"
    DATABASE_URL: str = "sqlite:///./savannah.db"

    # Local filtering configuration (override in .env as JSON arrays)
    FILTER_TITLE_KEYWORDS: list[str] = []
    FILTER_DESC_KEYWORDS: list[str] = []
    FILTER_COMPANY_DENY: list[str] = []
    FILTER_LOCATION_ALLOW: list[str] = []
    # Optional regex-based filters (case-insensitive)
    FILTER_TITLE_REGEX: list[str] = []
    FILTER_DESC_REGEX: list[str] = []
    # If true, keyword matching uses word boundaries to avoid partial matches (e.g., 'go' != 'django')
    FILTER_REQUIRE_WORD_BOUNDARIES: bool = False
    # Apply server-side filters to TheirStack request (default False = app-side filtering only)
    FILTER_APPLY_SERVER_SIDE: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()