from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: str
    cors_allowed_origins: str = ""
    max_request_body_bytes: int = Field(default=16_384, ge=1_024, le=1_048_576)
    app_env: Literal["development", "production"] = "development"
    auth_enabled: bool = False
    auth_username: str = ""
    auth_password: str = Field(default="", repr=False)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        try:
            url = make_url(value)
        except (ArgumentError, ValueError) as error:
            raise ValueError("DATABASE_URL must be a valid PostgreSQL connection URL") from error

        if (
            url.drivername != "postgresql+psycopg"
            or not url.host
            or not url.database
            or not url.username
            or not url.password
        ):
            raise ValueError(
                "DATABASE_URL must use postgresql+psycopg and include a host, "
                "database, username, and password"
            )

        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_cors_allowed_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        normalized_origins: list[str] = []
        for origin in origins:
            try:
                parsed = urlsplit(origin)
                invalid_port = parsed.port == 0
            except ValueError as error:
                raise ValueError("CORS_ALLOWED_ORIGINS must contain valid origins") from error
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or invalid_port
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or "?" in origin
                or "#" in origin
                or "*" in origin
            ):
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must contain explicit HTTP(S) origins without paths"
                )
            normalized_origins.append(origin.rstrip("/"))
        return ",".join(normalized_origins)

    @model_validator(mode="after")
    def validate_auth_configuration(self) -> "Settings":
        if self.auth_enabled and (
            not self.auth_username
            or ":" in self.auth_username
            or len(self.auth_username) > 128
            or not self.auth_password
        ):
            raise ValueError(
                "AUTH_ENABLED requires a username (without colons) and a password"
            )

        if self.app_env == "production":
            if not self.auth_enabled or len(self.auth_password) < 32:
                raise ValueError(
                    "Production requires AUTH_ENABLED and an AUTH_PASSWORD of at least "
                    "32 characters"
                )
            if not self.allowed_origins:
                raise ValueError(
                    "Production requires explicit CORS_ALLOWED_ORIGINS"
                )
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                raise ValueError(
                    "Production CORS_ALLOWED_ORIGINS must use HTTPS origins"
                )
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin for origin in self.cors_allowed_origins.split(",") if origin]


settings = Settings()
