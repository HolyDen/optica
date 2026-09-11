# Pass 5 — Surface

## Read
`spec/optica-plan-v1-core.md` §§ "Python API" and "`optica setup` — Machine
Initializer". Re-read § "Tech Stack" for the extras registry schema.

## Build
`src/optica/api/simple.py`, `src/optica/api/classifier.py`,
`src/optica/cli/setup.py`, and the registries.

Plus mirroring tests. The `--yes` prompt table and the `clip_threshold` bands
both give exact expected values — transcribe them.

## Record
The GPU-detected branch of `optica setup` is testable on this machine; the
no-GPU branch is not. Say which is which in `notes/build-log.md`.

## Out of scope
CI, README, CHANGELOG — all pass 6.

## Where to run
Run `optica setup` and the API check inside `.smoke/`.

## Done when
`optica.run()` works from Python and `optica setup` completes an idempotent
second run without redoing work.
