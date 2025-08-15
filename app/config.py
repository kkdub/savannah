# app/config.py

from __future__ import annotations
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    # — Core —
    SECRET_KEY: str = Field("change-me", description="JWT signing key")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60, ge=5, le=60 * 24)
    DEBUG: bool = True  # set False in prod

    # --- Database ---
    DATABASE_URL: str = Field("sqlite:///./savannah.db")
    # Alembic reads DB_URL from env; kept separate on purpose.

    # --- TheirStack / fetch job ---
    THEIRSTACK_API_KEY: Optional[str] = None
    THEIRSTACK_BASE: str = "https://api.theirstack.com"

    # --- Server-side filtering toggles ---
    FILTER_APPLY_SERVER_SIDE: bool = True

    # Titles to include/exclude (server-side). If empty, code can read from text files.
    FILTER_TITLE_KEYWORDS: List[str] = Field(default_factory=list)
    FILTER_TITLE_EXCLUDE: List[str] = Field(default_factory=list)

    # Optional description keywords (server-side, RE2-ish simple patterns)
    FILTER_DESC_KEYWORDS: List[str] = Field(default_factory=list)

    # Company deny list (merged with hardcoded IBM/Capgemini in fetcher)
    FILTER_COMPANY_DENY: List[str] = Field(default_factory=list)

    # Location allow list (merged with ["remote"] in fetcher)
    FILTER_LOCATION_ALLOW: List[str] = Field(default_factory=list)

    # Target countries for job search (defaults to high-wage markets)
    FILTER_TARGET_COUNTRIES: List[str] = Field(default_factory=lambda: ["US", "CH", "LU", "NO", "DK", "SG", "AU"])

    # Salary filtering (USD) - CRITICAL for management roles
    FILTER_MIN_SALARY_USD: Optional[int] = 120000
    FILTER_MAX_SALARY_USD: Optional[int] = 400000

    # Company size filtering (employees) - CRITICAL to avoid startups
    FILTER_MIN_EMPLOYEE_COUNT: Optional[int] = 500
    FILTER_MAX_EMPLOYEE_COUNT: Optional[int] = None  # No maximum - include large enterprises

    # Local (post-fetch) regex options
    FILTER_TITLE_REGEX: List[str] = Field(default_factory=list)
    FILTER_DESC_REGEX: List[str] = Field(default_factory=list)
    FILTER_REQUIRE_WORD_BOUNDARIES: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()