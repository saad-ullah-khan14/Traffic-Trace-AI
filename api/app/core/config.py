"""Application settings, loaded once from api/.env.

Import `settings` anywhere; never read os.environ directly elsewhere.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    EVIDENCE_DIR: str = "../evidence"
    CORS_ORIGINS: str = "http://localhost:3000"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Guards match decisions and the demo reset. Stops someone using an
    # unattended laptop mid-demo; not a defence against a network attacker.
    #
    # Deliberately has NO default: a default would mean a clone without a .env
    # silently accepts the PIN published in this repo's documentation, and the
    # only sign would be that it works. Missing it now fails at startup, next to
    # the DATABASE_URL error, naming the field.
    OFFICER_PIN: str

    # Phones load the dashboard at whatever address the hotspot hands out, so
    # the allowed origin cannot be known ahead of time. An explicit list would
    # block every phone request at preflight. This matches localhost plus the
    # private ranges a hotspot uses, on any port — and nothing routable from
    # the internet, which a bare wildcard would have allowed.
    CORS_ORIGIN_REGEX: str = (
        r"^http://("
        r"localhost"
        r"|127\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?$"
    )

    @property
    def cors_origins(self) -> list[str]:
        """CORS_ORIGINS is comma-separated in .env; FastAPI wants a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
