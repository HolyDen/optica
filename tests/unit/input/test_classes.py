"""Class-name rules, the blocklist, and the auto-mode class sequence.

Covers plan § "CLI Layer & Conventions" → *Class-name rules* (as amended
2026-09-13: leading ``-`` excluded), § "Input & Acquisition" → *Class-count
validation* and *Undefinable classes in auto modes*, and the ``--yes`` table's
overlap-warning and group-or-separate rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from optica.exceptions import OpticaValidationError
from optica.input import classes as cn


class TestFilesystemSafeNames:
    @pytest.mark.parametrize(
        "name",
        ["cat", "golden_retriever", "orange cat", "T-shirt", "a" * 50, "x.y", "café"],
    )
    def test_valid_names_pass(self, name):
        assert cn.class_name_problem(name) is None

    @pytest.mark.parametrize(
        ("name", "fragment"),
        [
            ("", "empty"),
            (".", "dots"),
            ("..", "dots"),
            ("....", "dots"),
            ("a/b", "path separator"),
            ("a\\b", "path separator"),
            ("cat,dog", "comma"),
            ("what?", "Windows"),
            ("a*b", "Windows"),
            ("a:b", "Windows"),
            ("a|b", "Windows"),
            ('a"b', "Windows"),
            ("a<b", "Windows"),
            ("a>b", "Windows"),
            ("a" * 51, "50 characters"),
            ("con", "reserved"),
            ("AUX", "reserved"),
            ("nul", "reserved"),
            ("prn", "reserved"),
            ("com1", "reserved"),
            ("com9", "reserved"),
            ("lpt1", "reserved"),
            ("LPT9", "reserved"),
            ("con.jpg", "reserved"),
        ],
    )
    def test_each_rule_names_its_reason(self, name, fragment):
        problem = cn.class_name_problem(name)
        assert problem is not None
        assert fragment in problem

    @pytest.mark.parametrize("name", ["--yes", "-y", "-cat", "--classes"])
    def test_a_leading_hyphen_is_rejected(self, name):
        # The amended clause: `optica fetch --classes --yes` parses cleanly with
        # classes == ["--yes"], and only this rule stops a folder called --yes.
        assert "begins with '-'" in (cn.class_name_problem(name) or "")

    def test_an_inner_hyphen_is_fine(self):
        assert cn.class_name_problem("golden-retriever") is None

    @pytest.mark.parametrize("name", ["com0", "com10", "lpt0", "console", "auxiliary"])
    def test_near_misses_of_reserved_names_pass(self, name):
        assert cn.class_name_problem(name) is None


class TestWholeListNormalization:
    def test_exact_duplicates_collapse_silently(self):
        assert cn.normalize_class_names(["cat", "dog", "cat"]) == ["cat", "dog"]

    def test_a_case_variant_is_a_hard_error_naming_both(self):
        with pytest.raises(OpticaValidationError) as info:
            cn.normalize_class_names(["cat", "Cat"])
        text = " ".join(info.value.fix)
        assert "'cat'" in text
        assert "'Cat'" in text

    def test_every_failing_name_is_listed_at_once(self):
        with pytest.raises(OpticaValidationError) as info:
            cn.normalize_class_names(["a/b", "--yes", "ok", "con"])
        assert info.value.message.startswith("3 class names")
        text = " ".join(info.value.fix)
        for name in ("'a/b'", "'--yes'", "'con'"):
            assert name in text

    def test_the_list_truncates_past_ten(self):
        bad = [f"-{i}" for i in range(13)]
        with pytest.raises(OpticaValidationError) as info:
            cn.normalize_class_names(bad)
        assert "(and 3 more)" in info.value.fix
        assert info.value.message.startswith("13 class names")

    def test_no_name_is_rewritten(self):
        with pytest.raises(OpticaValidationError):
            cn.normalize_class_names(["cat/"])

    def test_order_is_preserved(self):
        assert cn.normalize_class_names(["dog", "cat", "bird"]) == ["dog", "cat", "bird"]

    def test_list_names_truncates(self):
        names = [str(i) for i in range(12)]
        assert cn.list_names(names).endswith("(and 2 more)")
        assert cn.list_names(["a", "b"]) == "a, b"


class TestClassCount:
    def test_one_class_is_refused_with_the_plan_message(self):
        with pytest.raises(OpticaValidationError) as info:
            cn.require_min_classes(["cat"])
        assert info.value.message == "--classes requires at least 2 class names. Got: cat"

    def test_zero_is_invalid_identically(self):
        with pytest.raises(OpticaValidationError):
            cn.require_min_classes([])

    def test_two_pass(self):
        cn.require_min_classes(["cat", "dog"])


class TestBlocklist:
    @pytest.mark.parametrize(
        "name",
        [
            "other",
            "unknown",
            "misc",
            "miscellaneous",
            "none",
            "undefined",
            "various",
            "else",
            "rest",
            "good",
            "bad",
            "normal",
            "abnormal",
            "defective",
            "damaged",
            "broken",
            "working",
            "faulty",
            "mine",
            "yours",
            "safe",
            "unsafe",
            "valid",
            "invalid",
            "correct",
            "incorrect",
            "positive",
            "negative",
        ],
    )
    def test_every_seed_term_is_blocklisted(self, name):
        assert cn.is_blocklisted(name)

    @pytest.mark.parametrize("name", ["Other", "UNKNOWN", "Defective"])
    def test_matching_is_case_insensitive(self, name):
        assert cn.is_blocklisted(name)

    @pytest.mark.parametrize("name", ["not_cat", "non-defective", "no dog", "not"])
    def test_negated_terms(self, name):
        assert cn.is_blocklisted(name)

    @pytest.mark.parametrize(
        "name", ["class_a", "class_z", "label_1", "label_9", "Class A"]
    )
    def test_placeholder_labels(self, name):
        assert cn.is_blocklisted(name)

    @pytest.mark.parametrize("name", ["x", "7", "42"])
    def test_single_characters_and_lone_numbers(self, name):
        assert cn.is_blocklisted(name)

    @pytest.mark.parametrize(
        "name",
        [
            "cat",
            "golden_retriever",
            "notebook",
            "nonsense_word",
            "classroom",
            "bad_apple",
        ],
    )
    def test_concrete_names_pass(self, name):
        assert not cn.is_blocklisted(name)

    def test_the_list_is_extensible(self):
        # Implementation Note 10: adding a term is one entry in a frozenset.
        assert isinstance(cn.BLOCKLIST, frozenset)


class TestSubTermCounts:
    @pytest.mark.parametrize(
        ("images_per_class", "sub_terms", "expected"),
        [
            (50, 1, 50),
            (50, 2, 25),
            (50, 3, 16),  # floor division
            (50, 5, 10),
            (50, 6, 10),  # 8 → minimum 10, and the minimum wins
            (20, 3, 10),
            (100, 7, 14),
        ],
    )
    def test_floor_division_minimum_ten(self, images_per_class, sub_terms, expected):
        assert cn.sub_term_count(images_per_class, sub_terms) == expected

    def test_a_group_total_may_exceed_images_per_class(self):
        # Six sub-terms at the floor of 10 is 60 — above images_per_class 50.
        assert cn.sub_term_count(50, 6) * 6 == 60


class TestOverlaps:
    def test_substring_detection(self):
        overlaps = cn.find_overlaps(["cat", "wildcat", "dog"])
        assert overlaps == [cn.Overlap(inner="cat", outer="wildcat")]

    def test_case_and_separators_are_ignored(self):
        assert cn.find_overlaps(["Golden", "golden_retriever"])

    def test_no_overlap(self):
        assert cn.find_overlaps(["cat", "dog"]) == []


@dataclass
class _Scripted:
    """A prompter that answers from a script and records what it was asked."""

    definitions: dict[str, list[list[str]]] = field(default_factory=dict)
    group: bool = True
    overlap_answers: list[bool] = field(default_factory=list)
    new_lists: list[list[str]] = field(default_factory=list)
    confirm_answer: bool = True
    asked: list[str] = field(default_factory=list)
    confirmed_clean: list[bool] = field(default_factory=list)

    def define(self, name):
        self.asked.append(f"define:{name}")
        return self.definitions[name].pop(0)

    def group_or_separate(self, name, sub_terms):
        self.asked.append(f"group:{name}")
        return self.group

    def accept_overlaps(self, overlaps):
        self.asked.append("overlap")
        return self.overlap_answers.pop(0) if self.overlap_answers else True

    def redefine_classes(self, current):
        self.asked.append("classes")
        return self.new_lists.pop(0)

    def confirm(self, classes, *, clean):
        self.asked.append("confirm")
        self.confirmed_clean.append(clean)
        return self.confirm_answer


class TestAutoClassSequence:
    def test_clean_case_goes_straight_to_confirmation(self):
        prompter = _Scripted()
        resolved = cn.resolve_auto_classes(["cat", "dog"], 50, prompter)
        assert [(c.name, c.queries, c.per_query) for c in resolved] == [
            ("cat", ["cat"], 50),
            ("dog", ["dog"], 50),
        ]
        assert prompter.asked == ["confirm"]
        assert prompter.confirmed_clean == [True]

    def test_blocklisted_name_is_defined_then_grouped(self):
        prompter = _Scripted(
            definitions={"defective": [["cracked_screen", "dented_case"]]}
        )
        resolved = cn.resolve_auto_classes(["good_phone", "defective"], 50, prompter)
        grouped = resolved[1]
        assert grouped.name == "defective"
        assert grouped.grouped
        assert grouped.queries == ["cracked_screen", "dented_case"]
        assert grouped.per_query == 25
        assert grouped.target == 50
        assert prompter.asked == ["define:defective", "group:defective", "confirm"]
        # With a blocklisted name, confirmation still fires under --yes.
        assert prompter.confirmed_clean == [False]

    def test_separated_sub_terms_become_classes(self):
        prompter = _Scripted(
            definitions={"defective": [["cracked_screen", "dented_case"]]}, group=False
        )
        resolved = cn.resolve_auto_classes(["intact_phone", "defective"], 50, prompter)
        assert [c.name for c in resolved] == [
            "intact_phone",
            "cracked_screen",
            "dented_case",
        ]
        assert all(not c.grouped for c in resolved[1:])

    def test_a_definition_that_is_empty_is_refused(self):
        prompter = _Scripted(definitions={"other": [[]]})
        with pytest.raises(OpticaValidationError):
            cn.resolve_auto_classes(["cat", "other"], 50, prompter)

    def test_declining_an_overlap_reopens_the_class_list_and_resumes(self):
        prompter = _Scripted(overlap_answers=[False, True], new_lists=[["cat", "dog"]])
        resolved = cn.resolve_auto_classes(["cat", "wildcat"], 50, prompter)
        assert [c.name for c in resolved] == ["cat", "dog"]
        assert prompter.asked == ["overlap", "classes", "confirm"]

    def test_declining_an_overlap_in_a_sub_term_reopens_its_definition_only(self):
        prompter = _Scripted(
            definitions={"other": [["cat_toy", "ball"], ["yarn", "ball"]]},
            overlap_answers=[False],
        )
        resolved = cn.resolve_auto_classes(["cat", "other"], 50, prompter)
        # The group answer is kept: group_or_separate is asked exactly once.
        assert prompter.asked.count("group:other") == 1
        assert prompter.asked == [
            "define:other",
            "group:other",
            "overlap",
            "define:other",
            "confirm",
        ]
        assert resolved[1].queries == ["yarn", "ball"]

    def test_declined_confirmation_returns_nothing(self):
        prompter = _Scripted(confirm_answer=False)
        assert cn.resolve_auto_classes(["cat", "dog"], 50, prompter) == []

    def test_fewer_than_two_after_resolution_is_refused(self):
        prompter = _Scripted(definitions={"other": [["cat"]]})
        with pytest.raises(OpticaValidationError):
            cn.resolve_auto_classes(["other"], 50, prompter)

    def test_separation_that_creates_a_case_clash_is_refused(self):
        prompter = _Scripted(definitions={"other": [["Cat", "Dog"]]}, group=False)
        with pytest.raises(OpticaValidationError):
            cn.resolve_auto_classes(["cat", "other"], 50, prompter)

    def test_a_definition_is_validated_as_class_names(self):
        prompter = _Scripted(definitions={"other": [["--yes", "dog"]]})
        with pytest.raises(OpticaValidationError):
            cn.resolve_auto_classes(["cat", "other"], 50, prompter)
