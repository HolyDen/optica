"""The config package's re-exports.

Mirrors ``src/optica/config/__init__.py``. It holds no logic of its own, but it
is the import path the rest of the package uses, so a name that stops resolving
should fail here rather than at a call site three passes later.
"""

from __future__ import annotations

import optica.config as config_package
from optica.config import defaults, manager, schema


class TestReExports:
    def test_every_declared_name_resolves(self):
        for name in config_package.__all__:
            assert hasattr(config_package, name), name

    def test_they_are_the_same_objects_as_their_modules(self):
        assert config_package.DEFAULTS is defaults.DEFAULTS
        assert config_package.DEFAULT_TASK == defaults.DEFAULT_TASK
        assert config_package.ConfigManager is manager.ConfigManager
        assert config_package.ResolvedConfig is manager.ResolvedConfig
        assert config_package.Source is manager.Source
        assert config_package.OpticaConfig is schema.OpticaConfig

    def test_importing_it_does_not_import_torch(self):
        import sys

        assert "torch" not in sys.modules
