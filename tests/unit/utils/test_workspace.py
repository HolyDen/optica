"""Creating the folders Optica owns, gitignored on the way in.

Covers plan § "Project layout" l.289: ``./checkpoints/`` and ``./optica-output/``
are gitignored, Optica drops a ``.gitignore`` containing ``*`` inside either
folder when it first creates it, and it never touches the user's own ignore
files.

Every test here constructs the folder state in its own body — an existing
folder, an existing folder with the user's own ``.gitignore``, a missing parent
chain — rather than relying on what an earlier test left behind, because the
whole behaviour turns on whether the folder was there a moment ago.
"""

from __future__ import annotations

from optica.utils import workspace


class TestCreateIgnored:
    """The creation case: l.289's first clause."""

    def test_it_creates_the_folder(self, tmp_path):
        target = tmp_path / "optica-output"
        assert not target.exists()
        workspace.create_ignored(target)
        assert target.is_dir()

    def test_the_gitignore_lands_inside_that_folder(self, tmp_path):
        target = tmp_path / "checkpoints"
        workspace.create_ignored(target)
        assert (target / ".gitignore").is_file()
        # l.289: "a .gitignore containing `*`".
        assert (target / ".gitignore").read_text(encoding="utf-8") == "*\n"

    def test_nothing_is_written_beside_the_folder(self, tmp_path):
        # "inside that folder" — the parent is the user's project directory.
        workspace.create_ignored(tmp_path / "optica-output")
        assert not (tmp_path / ".gitignore").exists()

    def test_it_reports_that_it_created_the_folder(self, tmp_path):
        assert workspace.create_ignored(tmp_path / "checkpoints") is True

    def test_missing_parents_are_created_but_only_the_target_is_ignored(self, tmp_path):
        target = tmp_path / "nested" / "deeper" / "optica-output"
        workspace.create_ignored(target)
        assert target.is_dir()
        assert (target / ".gitignore").is_file()
        # l.289 names the folder, not the chain leading to it.
        assert not (tmp_path / "nested" / ".gitignore").exists()
        assert not (tmp_path / "nested" / "deeper" / ".gitignore").exists()


class TestAFolderThatAlreadyExists:
    """The case l.289 does not settle, and the reading taken.

    l.289's trigger is *when Optica first creates either folder*. A folder that
    is already there was not created by this call, so nothing is written. That
    reading is what makes the second clause — Optica never touches the user's
    ignore files — hold without a special case: the only directory written into
    is one that did not exist a moment earlier.
    """

    def test_an_existing_folder_gets_no_gitignore(self, tmp_path):
        target = tmp_path / "optica-output"
        target.mkdir()
        workspace.create_ignored(target)
        assert not (target / ".gitignore").exists()

    def test_it_reports_that_it_created_nothing(self, tmp_path):
        target = tmp_path / "checkpoints"
        target.mkdir()
        assert workspace.create_ignored(target) is False

    def test_a_users_own_gitignore_survives_untouched(self, tmp_path):
        target = tmp_path / "optica-output"
        target.mkdir()
        mine = target / ".gitignore"
        mine.write_text("!keep-this.txt\n*.tmp\n", encoding="utf-8")
        workspace.create_ignored(target)
        assert mine.read_text(encoding="utf-8") == "!keep-this.txt\n*.tmp\n"

    def test_existing_contents_are_left_alone(self, tmp_path):
        target = tmp_path / "checkpoints"
        target.mkdir()
        (target / "checkpoint_val0.900_epoch3").mkdir()
        workspace.create_ignored(target)
        assert (target / "checkpoint_val0.900_epoch3").is_dir()

    def test_a_second_call_does_not_rewrite_the_file(self, tmp_path):
        target = tmp_path / "optica-output"
        workspace.create_ignored(target)
        (target / ".gitignore").write_text("edited by hand\n", encoding="utf-8")
        # A later run finds the folder present and leaves the edit standing.
        assert workspace.create_ignored(target) is False
        assert (target / ".gitignore").read_text(encoding="utf-8") == "edited by hand\n"


class TestTheContract:
    """What the module publishes, and what it deliberately does not cover."""

    def test_the_body_is_the_plans_value(self):
        assert workspace.GITIGNORE_BODY.strip() == "*"

    def test_the_filename(self):
        assert workspace.GITIGNORE_FILE == ".gitignore"

    def test_dataset_is_not_gitignored_by_any_call_site(self):
        # The plan gitignores exactly two folders and `dataset/` is not one of
        # them — it is the user's curated data. This pins the call sites, so
        # extending the helper to `dataset/` fails here rather than silently
        # adding an ignore file to data someone meant to commit.
        import pathlib

        src = pathlib.Path(workspace.__file__).resolve().parents[1]
        callers = [
            line.strip()
            for path in src.rglob("*.py")
            for line in path.read_text(encoding="utf-8").splitlines()
            if "create_ignored(" in line and "def " not in line
        ]
        assert callers, "no call sites found — the search is wrong, not the code"
        assert not [c for c in callers if "dataset" in c], callers
