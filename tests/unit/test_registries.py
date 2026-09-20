"""The task and extras registries.

Covers plan § "`optica setup` — Machine Initializer" → *Registry and resolution*
(the schema, the two registries, `resolve_setup`'s fixed modifier order, group
semantics, torch's universality) and *`--include-extras` / `--exclude-extras`
parsing* (vocabulary, pip-name and typo suggestions, group handling, conflicts,
empty values), plus the Review's download total and the `cu<XXX>` index the
pre-implementation gate pinned.

The `size_estimate` values and the Review's `~0.9–3.1GB` total are transcribed
from the plan as exact expected values, not recomputed from the code under test.
"""

from __future__ import annotations

import pytest

from optica import registries as reg
from optica.exceptions import OpticaValidationError

# Transcribed from plan § "Registry and resolution" (l.484, l.488, l.492) and the
# extras prompt (l.420-422). The en dash is the plan's own character.
EXPECTED_SIZES = {
    "web": "~5MB",
    "clip": "~600MB",
    "torch-auto": "~250MB–2.5GB",
    "torch-cpu": "~250MB",
    "torch-gpu": "~2–2.5GB",
}

# The Review example at l.437-450: torch-auto + web + clip.
REVIEW_SELECTION = {"torch-auto", "web", "clip"}
REVIEW_TOTAL = "~0.9–3.1GB"


class TestSchema:
    def test_the_registry_holds_exactly_the_five_v1_entries(self):
        assert sorted(reg.EXTRAS_REGISTRY) == [
            "clip",
            "torch-auto",
            "torch-cpu",
            "torch-gpu",
            "web",
        ]

    @pytest.mark.parametrize("key", sorted(EXPECTED_SIZES))
    def test_every_entry_carries_the_four_required_fields(self, key):
        entry = reg.EXTRAS_REGISTRY[key]
        assert isinstance(entry["display_name"], str) and entry["display_name"]
        assert isinstance(entry["default"], bool)
        assert isinstance(entry["size_estimate"], str) and entry["size_estimate"]
        assert entry["enables"] and all(isinstance(e, str) for e in entry["enables"])

    @pytest.mark.parametrize("key", sorted(EXPECTED_SIZES))
    def test_pip_extra_xor_index_url(self, key):
        entry = reg.EXTRAS_REGISTRY[key]
        assert ("pip_extra" in entry) is not ("index_url" in entry)

    @pytest.mark.parametrize(("key", "expected"), sorted(EXPECTED_SIZES.items()))
    def test_size_estimates_are_the_plans_own_strings(self, key, expected):
        assert reg.EXTRAS_REGISTRY[key]["size_estimate"] == expected

    def test_the_defaults_are_torch_auto_and_web(self):
        defaults = {k for k, v in reg.EXTRAS_REGISTRY.items() if v["default"]}
        assert defaults == {"torch-auto", "web"}

    def test_torch_is_universal_and_never_task_relevant(self):
        universal = {k for k, v in reg.EXTRAS_REGISTRY.items() if v.get("universal")}
        assert universal == reg.group_members("torch", reg.EXTRAS_REGISTRY)
        for task in reg.TASK_REGISTRY:
            assert not universal & set(task["relevant_extras"])

    def test_one_task_whose_namespace_and_tier5_class_are_the_plans(self):
        [task] = reg.TASK_REGISTRY
        assert task["task_id"] == "classify"
        assert task["api_namespace"] == "optica.classify"
        assert task["tier5_class"] == "Classifier"
        assert task["cli_group"] == "classify"
        assert task["relevant_extras"] == ["web", "clip"]

    def test_the_four_setup_packages_partition_by_index(self):
        assert reg.SETUP_PACKAGES == ("torch", "torchvision", "timm", "scikit-learn")
        assert set(reg.INDEXED_PACKAGES) | set(reg.PYPI_PACKAGES) == set(
            reg.SETUP_PACKAGES
        )
        assert not set(reg.INDEXED_PACKAGES) & set(reg.PYPI_PACKAGES)


class TestPromptOrder:
    def test_torch_then_web_then_clip(self):
        relevant = set(reg.EXTRAS_REGISTRY)
        assert reg.prompt_order(relevant)[:3] == [
            "torch-auto",
            "torch-cpu",
            "torch-gpu",
        ]
        assert reg.prompt_order(relevant)[3:] == ["web", "clip"]


class TestDownloadTotal:
    def test_the_reviews_breakdown_and_its_total(self):
        rows = reg.size_breakdown(REVIEW_SELECTION)
        assert rows == [
            ("PyTorch stack (auto-detect)", "~250MB–2.5GB"),
            ("Browser UI", "~5MB"),
            ("CLIP filtering", "~600MB"),
        ]
        assert reg.download_total(REVIEW_SELECTION) == REVIEW_TOTAL

    def test_the_total_reconciles_to_the_rows_it_is_printed_under(self):
        rows = [reg.parse_size_estimate(size) for _, size in
                reg.size_breakdown(REVIEW_SELECTION)]
        assert sum(row.low for row in rows) == 855.0  # 250 + 5 + 600
        assert sum(row.high for row in rows) == 3105.0  # 2500 + 5 + 600

    @pytest.mark.parametrize(
        ("estimate", "low", "high"),
        [
            ("~5MB", 5.0, 5.0),
            ("~600MB", 600.0, 600.0),
            ("~250MB", 250.0, 250.0),
            ("~250MB–2.5GB", 250.0, 2500.0),
            ("~2–2.5GB", 2000.0, 2500.0),
        ],
    )
    def test_every_shape_the_registry_uses_parses(self, estimate, low, high):
        parsed = reg.parse_size_estimate(estimate)
        assert (parsed.low, parsed.high) == (low, high)

    def test_an_unreadable_estimate_is_a_defect_not_a_user_error(self):
        with pytest.raises(ValueError, match="unreadable size_estimate"):
            reg.parse_size_estimate("about a gigabyte")

    @pytest.mark.parametrize(
        ("selection", "expected"),
        [
            (set(), "none selected"),
            ({"web"}, "~5MB"),
            ({"web", "clip"}, "~605MB"),
            ({"torch-cpu", "web"}, "~255MB"),
            ({"torch-gpu", "web", "clip"}, "~2.6–3.1GB"),
            ({"torch-auto"}, "~0.3–2.5GB"),
        ],
    )
    def test_totals_under_and_over_a_gigabyte(self, selection, expected):
        assert reg.download_total(selection) == expected


class TestCudaIndex:
    @pytest.mark.parametrize(
        ("driver", "expected"),
        [
            ("13.1", "https://download.pytorch.org/whl/cu130"),
            ("13.0", "https://download.pytorch.org/whl/cu130"),
            ("13.2", "https://download.pytorch.org/whl/cu132"),
            ("12.7", "https://download.pytorch.org/whl/cu126"),
            ("12.6", "https://download.pytorch.org/whl/cu126"),
        ],
    )
    def test_the_newest_published_index_the_driver_can_run(self, driver, expected):
        assert reg.cuda_index_url(driver) == expected

    @pytest.mark.parametrize("driver", [None, "", "11.8", "not-a-version"])
    def test_no_usable_cuda_falls_to_the_cpu_index(self, driver):
        assert reg.cuda_index_url(driver) == reg.CPU_INDEX

    def test_cu131_is_never_produced_because_it_was_never_published(self):
        published = {url for _, url in reg.CUDA_INDEXES}
        assert "https://download.pytorch.org/whl/cu131" not in published
        # The whole span a 13.x driver can report, none of it string-built.
        produced = {reg.cuda_index_url(f"13.{minor}") for minor in range(0, 9)}
        assert "https://download.pytorch.org/whl/cu131" not in produced

    def test_torch_gpus_pinned_index_is_the_gates_answer(self):
        assert (
            reg.EXTRAS_REGISTRY["torch-gpu"]["index_url"]
            == "https://download.pytorch.org/whl/cu130"
        )
        assert reg.EXTRAS_REGISTRY["torch-auto"]["index_url"] is None
        assert reg.EXTRAS_REGISTRY["torch-cpu"]["index_url"] == reg.CPU_INDEX


def _resolve(**kwargs) -> set[str]:
    args = reg.SetupArgs(**kwargs)
    reg.validate_extras_selection(args)
    _, extras = reg.resolve_setup(args)
    return extras


class TestResolveSetup:
    def test_all_extras_collapses_each_group_to_its_default(self):
        assert _resolve(all_extras=True) == {"torch-auto", "web", "clip"}

    def test_no_extras_selects_nothing(self):
        assert _resolve(no_extras=True) == set()

    def test_a_flag_makes_the_base_the_defaults(self):
        assert _resolve(include_extras=["clip"]) == {"torch-auto", "web", "clip"}

    def test_an_empty_include_is_a_no_op_that_still_resolves_the_defaults(self):
        # `--include-extras ""`, the unset-shell-variable case.
        assert _resolve(include_extras=[]) == {"torch-auto", "web"}
        assert reg.SetupArgs(include_extras=[]).non_interactive is True

    def test_exclude_torch_removes_every_variant(self):
        assert _resolve(exclude_extras=["torch"]) == {"web"}

    def test_an_explicit_include_displaces_its_groups_other_member(self):
        assert _resolve(all_extras=True, include_extras=["torch-cpu"]) == {
            "torch-cpu",
            "web",
            "clip",
        }

    def test_the_modifier_order_is_fixed_not_the_flags_order(self):
        # Include then exclude, whichever way round they were written.
        first = _resolve(include_extras=["clip"], exclude_extras=["web"])
        second = _resolve(exclude_extras=["web"], include_extras=["clip"])
        assert first == second == {"torch-auto", "clip"}

    def test_the_interactive_path_is_what_the_prompt_returns(self):
        asked: list[list[str]] = []

        def select(keys: list[str]) -> list[str]:
            asked.append(keys)
            return ["web"]

        args = reg.SetupArgs()
        assert args.non_interactive is False
        _, extras = reg.resolve_setup(args, select_extras=select)
        assert extras == {"web"}
        assert asked == [["torch-auto", "torch-cpu", "torch-gpu", "web", "clip"]]

    def test_the_one_task_selects_itself_with_no_prompt(self):
        tasks, _ = reg.resolve_setup(reg.SetupArgs(all_extras=True))
        assert tasks == {"classify"}


class TestValidation:
    def test_an_unknown_name_lists_every_valid_key(self):
        with pytest.raises(OpticaValidationError) as info:
            reg.validate_extras_selection(reg.SetupArgs(include_extras=["zzzzzzz"]))
        assert info.value.options == [
            "clip",
            "torch-auto",
            "torch-cpu",
            "torch-gpu",
            "web",
        ]
        assert info.value.fix == []

    @pytest.mark.parametrize(
        ("typed", "hint"),
        [
            ("optica[clip]", "clip"),
            ("open-clip-torch", "clip"),
            ("optica[web]", "web"),
            ("fastapi", "web"),
            ("torch", "torch-auto"),
            ("wbe", "web"),
            ("torch-gpo", "torch-gpu"),
        ],
    )
    def test_a_close_name_is_named_back(self, typed, hint):
        with pytest.raises(OpticaValidationError) as info:
            reg.validate_extras_selection(reg.SetupArgs(include_extras=[typed]))
        assert f"Did you mean '{hint}'?" in " ".join(info.value.fix)

    def test_every_invalid_value_is_reported_at_once(self):
        with pytest.raises(OpticaValidationError) as info:
            reg.validate_extras_selection(
                reg.SetupArgs(include_extras=["wbe"], exclude_extras=["clpi"])
            )
        assert "wbe" in info.value.message
        assert "clpi" in info.value.message
        assert "Did you mean 'web'?" in " ".join(info.value.fix)
        assert "Did you mean 'clip'?" in " ".join(info.value.fix)

    def test_a_group_name_is_valid_to_exclude_and_not_to_include(self):
        reg.validate_extras_selection(reg.SetupArgs(exclude_extras=["torch"]))
        with pytest.raises(OpticaValidationError, match="Not a known extra: torch"):
            reg.validate_extras_selection(reg.SetupArgs(include_extras=["torch"]))

    def test_two_members_of_one_group_is_a_hard_error(self):
        with pytest.raises(OpticaValidationError, match="more than one member"):
            reg.validate_extras_selection(
                reg.SetupArgs(include_extras=["torch-cpu", "torch-gpu"])
            )

    def test_the_same_extra_on_both_sides_is_a_hard_error(self):
        with pytest.raises(OpticaValidationError, match="in both --include-extras"):
            reg.validate_extras_selection(
                reg.SetupArgs(include_extras=["clip"], exclude_extras=["clip"])
            )

    def test_the_conflict_is_compared_after_group_expansion(self):
        with pytest.raises(OpticaValidationError, match="torch-cpu is in both"):
            reg.validate_extras_selection(
                reg.SetupArgs(include_extras=["torch-cpu"], exclude_extras=["torch"])
            )

    def test_a_redundant_combination_is_silently_accepted(self):
        # `--exclude-extras clip` with clip not selected adds nothing and is not
        # an error: a flag asking for something already true is a no-op.
        reg.validate_extras_selection(reg.SetupArgs(exclude_extras=["clip"]))
        assert _resolve(exclude_extras=["clip"]) == {"torch-auto", "web"}
