"""``tests/unit/`` mirrors the source tree.

`CLAUDE.md` § "Tests" states the rule; this makes it checkable. Two modules
reached pass 1's end with no test file — ``config/schema.py`` and
``cli/__init__.py``, the second of which holds the comma value-separator
convention — and the gap was found by hand rather than by anything that runs.

A module with no test file fails here. A module that genuinely holds no code is
named in ``_NO_LOGIC`` below, so skipping one is a deliberate, visible act rather
than an omission.
"""

from __future__ import annotations

import pathlib

import pytest

_SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "optica"
_UNIT = pathlib.Path(__file__).resolve().parent

_NO_LOGIC: frozenset[str] = frozenset(
    {
        # A docstring and `from __future__ import annotations`. Nothing to assert
        # that would not be asserting Python's import system.
        "utils/__init__.py",
    }
)

_RENAMED: dict[str, str] = {
    # A bare `test_config.py` in tests/unit/cli/ reads as a mirror of `config/`
    # rather than of the `optica config` command.
    "cli/config.py": "test_config_command.py",
}


def _expected_mirror(module: pathlib.Path) -> pathlib.Path:
    relative = module.relative_to(_SRC)
    key = relative.as_posix()
    if key in _RENAMED:
        return _UNIT / relative.parent / _RENAMED[key]
    stem = relative.stem
    name = "test_init.py" if stem == "__init__" else f"test_{stem}.py"
    return _UNIT / relative.parent / name


def _source_modules() -> list[pathlib.Path]:
    return sorted(_SRC.rglob("*.py"))


class TestMirror:
    def test_the_source_tree_is_not_empty(self):
        # A glob that matched nothing would make every assertion below vacuous.
        assert len(_source_modules()) >= 16

    @pytest.mark.parametrize(
        "module", _source_modules(), ids=lambda p: p.relative_to(_SRC).as_posix()
    )
    def test_every_module_has_a_test_file(self, module):
        key = module.relative_to(_SRC).as_posix()
        if key in _NO_LOGIC:
            pytest.skip(f"{key} holds no code; see _NO_LOGIC")
        assert _expected_mirror(module).exists(), (
            f"{key} has no test file; expected "
            f"{_expected_mirror(module).relative_to(_UNIT.parents[1])}"
        )

    @pytest.mark.parametrize("key", sorted(_NO_LOGIC))
    def test_the_exemptions_are_still_empty(self, key):
        # An exempt module that grows code must lose its exemption.
        body = [
            line.strip()
            for line in (_SRC / key).read_text(encoding="utf-8").splitlines()
            if line.strip()
            and not line.strip().startswith("#")
            and line.strip() != "from __future__ import annotations"
        ]
        # What remains should be the module docstring and nothing else.
        declarations = ("def ", "class ", "import ", "from ")
        assert not any(
            line.startswith(declarations) for line in body
        ), f"{key} has grown code and should no longer be exempt"

    @pytest.mark.parametrize("key", sorted(_NO_LOGIC | set(_RENAMED)))
    def test_the_lists_name_modules_that_exist(self, key):
        # A stale entry would silently exempt nothing and hide a real gap.
        assert (_SRC / key).exists(), f"{key} is listed but no longer exists"
