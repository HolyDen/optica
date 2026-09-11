# Pass 6 — Packaging and documentation

**No `src/` code in this pass.**

## Read
`spec/optica-plan-v1-core.md` § "Documentation" and § "Tech Stack".
Also `notes/build-log.md` in full — assumptions logged across six passes may
need saying out loud in the README.

## Build
- `.github/workflows/ci.yml` — **extend** the minimal workflow from pass 1 to
  the full version matrix the plan specifies, keeping the three runners from
  pass 1, and add the `optica setup --ci` step now that it exists. CI never installs the torch stack;
  `@pytest.mark.slow` tests do not run there.
- `README.md` — finalize for V1. The CI badge placeholder comment marks where
  the badge goes, but leave it commented until CI has actually passed.
- `CHANGELOG.md` — minimum entry is exactly `## [0.2.0] — Initial release.`
- Confirm the version classifiers landed in `pyproject.toml` in pass 0.
- The README states platform support. Linux and macOS are primary targets;
  Windows is covered by CI but is not a primary target. Do not describe
  Windows as untested.

## Do not
Change `version` in `pyproject.toml`. It says `0.1.1` deliberately, so that an
accidental upload fails as a duplicate rather than burning `0.2.0`.

## Known limit
A GitHub Actions workflow cannot be verified without pushing, and `git push` is
denied to the agent. The milestone here is a valid, complete workflow file —
the green check comes after a human pushes it, as at every pass boundary since
pass 1.

## Done when
The workflow file parses as valid YAML, README and CHANGELOG are complete, and
the full test suite passes locally including the slow tests.
