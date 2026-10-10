"""Configuration: validation limits (constants) and runtime settings (paths, DB URL)."""
import os
from dataclasses import dataclass
from pathlib import Path

# ---- Validation limits (documented in README) ----
MAX_BATCH_SIZE = 500
MAX_NAME_LEN = 100
MAX_EMAIL_LEN = 254
MAX_TITLE_LEN = 100
MAX_EVENT_LEN = 150
MAX_ORG_LEN = 150
DEFAULT_CERTIFICATE_TITLE = "Certificate of Completion"


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Tests build their own Settings pointing at temp locations."""

    database_url: str = "sqlite:///./app.db"
    output_dir: Path = Path("generated_certificates")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv("DATABASE_URL", "sqlite:///./app.db"),
            output_dir=Path(os.getenv("CERTIFICATE_OUTPUT_DIR", "generated_certificates")),
        )
