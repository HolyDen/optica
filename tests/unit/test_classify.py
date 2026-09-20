"""``optica.classify`` — the canonical, task-namespaced surface.

Covers plan § "Python API" → *Canonical surface — task-namespaced from V1*: the
namespace ships in V1, the flat forms are aliases of its own functions, and
alias resolution consults ``DEFAULT_TASK`` rather than hardcoding "classify".
"""

from __future__ import annotations

import optica
from optica import classify
from optica.config.defaults import DEFAULT_TASK


class TestNamespace:
    def test_it_carries_the_tier_3_and_tier_4_functions(self):
        assert sorted(
            name for name in classify.__all__ if name.islower()
        ) == ["curate", "export", "fetch", "label", "run", "train"]

    def test_the_flat_forms_are_this_namespaces_own_functions(self):
        for name in ("run", "fetch", "label", "curate", "train", "export"):
            assert getattr(optica, name) is getattr(classify, name)

    def test_it_carries_the_tier_5_class_and_the_config_objects(self):
        assert classify.Classifier is optica.Classifier
        for name in ("FetchConfig", "TrainConfig", "ExportConfig"):
            assert getattr(classify, name) is getattr(optica, name)

    def test_alias_resolution_goes_through_default_task(self):
        # Not "classify" as a literal: a post-V1 task slots in by changing the
        # constant, exactly as the CLI's flat aliases do.
        assert DEFAULT_TASK == "classify"
        assert optica._TASKS[DEFAULT_TASK] is classify

    def test_the_task_registry_describes_this_namespace(self):
        from optica.registries import TASK_REGISTRY

        [task] = TASK_REGISTRY
        assert task["api_namespace"] == f"optica.{DEFAULT_TASK}"
        assert getattr(optica, task["tier5_class"]) is classify.Classifier
