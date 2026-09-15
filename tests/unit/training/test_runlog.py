"""The training log.

Covers plan § "Training" → *Training log*:
``run_<YYYYMMDD>_<HHMMSS>_<model>_<N>classes.json``, ``run_id`` matching the
filename's timestamp, both copies written together and after every epoch, and
``log_file`` stored in tilde form.
"""

from __future__ import annotations

from datetime import datetime

from optica.training import runlog


class TestNames:
    def test_run_id_is_year_inclusive(self):
        assert runlog.run_id_for(datetime(2026, 3, 12, 14, 30, 22)) == "20260312_143022"

    def test_the_plans_filename(self):
        assert (
            runlog.log_filename("20260312_143022", "efficientnet-small", 3)
            == "run_20260312_143022_efficientnet-small_3classes.json"
        )


class TestTildePath:
    def test_under_home_it_is_tilde_form_with_forward_slashes(self, tmp_path):
        home = tmp_path / "home"
        path = home / ".optica" / "logs" / "run.json"
        path.parent.mkdir(parents=True)
        assert runlog.tilde_path(path, home) == "~/.optica/logs/run.json"

    def test_outside_home_it_is_left_as_it_is(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        elsewhere = tmp_path / "other" / "run.json"
        assert runlog.tilde_path(elsewhere, home) == str(elsewhere)


class TestWriting:
    def test_both_copies_are_written_and_identical_after_each_epoch(self, tmp_path):
        a = tmp_path / "home" / ".optica" / "logs" / "run.json"
        b = tmp_path / "optica-output" / "logs" / "run.json"
        log = runlog.RunLog([a, b], {"run_id": "r", "epochs": []})
        log.write()
        log.record_epoch({"epoch": 1, "val_loss": 0.5})
        assert a.read_bytes() == b.read_bytes()
        log.record_epoch({"epoch": 2, "val_loss": 0.4})
        assert '"epoch": 2' in b.read_text(encoding="utf-8")
        assert a.read_bytes() == b.read_bytes()

    def test_truncate_drops_later_epochs(self):
        log = runlog.RunLog([], {"epochs": [{"epoch": i} for i in range(1, 6)]})
        log.truncate_after(3)
        assert [e["epoch"] for e in log.data["epochs"]] == [1, 2, 3]
