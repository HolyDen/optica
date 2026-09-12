"""Configuration: built-in defaults, the schema, and priority resolution.

Implements plan § "Configuration".
"""

from __future__ import annotations

from optica.config.defaults import DEFAULT_TASK, DEFAULTS
from optica.config.manager import ConfigManager, ResolvedConfig, Source
from optica.config.schema import OpticaConfig

__all__ = [
    "DEFAULTS",
    "DEFAULT_TASK",
    "ConfigManager",
    "OpticaConfig",
    "ResolvedConfig",
    "Source",
]
