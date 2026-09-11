# Pass 4 — Training and export

**The first pass that needs torch.** Install it before starting.

## Read
`spec/optica-plan-v1-core.md` §§ "Training" and "Export".
Also `notes/verified.md` — Task 4 holds the per-backbone unfreeze layer names,
`crop_pct` and `interpolation`. Use those values; do not re-derive them from
memory.

## Build
`src/optica/training/`, `src/optica/export/`, and `src/optica/input/clip.py`.

`tests/conftest.py` gains the synthetic `pretrained=False` fixtures the plan
specifies. Everything importing torch is marked `@pytest.mark.slow`.

## Record
This machine has an NVIDIA GPU, so the CUDA device path is genuinely exercised.
**The MPS path will be written but never run** — note that in
`notes/build-log.md` so it is not later mistaken for tested code.

The plan states expected values for the split arithmetic and the phase epoch
allocation. Transcribe them into stubs.

## Out of scope
`api/`, `cli/setup.py`.

## Where to run
Run training end to end inside `.smoke/`, never at the repo root.

## Done when
`optica train` and `optica export` both run to completion on a small real
dataset.
