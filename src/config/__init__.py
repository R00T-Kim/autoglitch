"""Configuration validation package."""

from .schema import parse_autoglitch_config, validate_autoglitch_config
from .validator import validate_config

__all__ = ["validate_config", "parse_autoglitch_config", "validate_autoglitch_config"]
