"""snowwatch: competitive displacement signal monitor for Snowflake."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

__version__ = "0.1.0"

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path | None = None) -> None:
    """Load the repo-root .env; real environment variables take precedence."""
    load_dotenv(path or _ENV_PATH, override=False)


# Runs before config reads os.environ: importing any submodule executes this
# package init first.
load_env()
