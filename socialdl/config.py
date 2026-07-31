"""Configuration loading and value resolution.

Precedence for every setting is: explicit value > environment variable >
config file (~/.config/socialdl/config.toml) > built-in default.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

# Project root is the parent of this package directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = PROJECT_ROOT / "downloads"

CONFIG_PATH = Path(
    os.environ.get("SOCIALDL_CONFIG", Path.home() / ".config" / "socialdl" / "config.toml")
)


def load_config() -> dict:
    """Read the TOML config file, or return {} if it's missing/unreadable."""
    if tomllib is None or not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    except Exception as exc:  # a bad config shouldn't block work
        sys.stderr.write(f"warning: ignoring bad config {CONFIG_PATH}: {exc}\n")
        return {}


def resolve(value, env_key: str, cfg: dict, cfg_key: str, default=None):
    """Precedence: explicit value > environment variable > config > default."""
    if value is not None:
        return value
    if os.environ.get(env_key):
        return os.environ[env_key]
    if cfg.get(cfg_key) is not None:
        return cfg[cfg_key]
    return default


def resolve_bool(value: bool, env_key: str, cfg: dict, cfg_key: str) -> bool:
    """A boolean that can be turned on by explicit value, env var, or config."""
    if value:
        return True
    env = os.environ.get(env_key)
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    return bool(cfg.get(cfg_key, False))
