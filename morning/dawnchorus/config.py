"""Load morning/config.toml."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.toml"


def load(path=CONFIG_PATH):
    with open(path, "rb") as f:
        return tomllib.load(f)


def resolve(rel):
    """Paths in config.toml are relative to morning/."""
    p = Path(rel)
    return p if p.is_absolute() else ROOT / p
