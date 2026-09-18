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

## From the fast-follow reconciliation

The plan was amended at 18 lines — l.104, l.112, l.220, l.261,
l.289, l.799, l.853, l.949, l.1155, l.1165, l.1284, l.1374, l.1378, l.1394,
l.1419, l.1570, l.1642, l.1649. No line number moved. **Read those lines in
`spec/`**; this section summarises them and is not an authority over them.
Pass 5 is the last pass that writes `src/`.

1. **`TrainConfig` has exactly eleven fields** — `epochs`, `batch_size`,
   `learning_rate`, `augmentation`, `early_stopping`, `finetune_ratio`,
   `optimizer`, `max_checkpoints`, `train_split`, `val_split`, `test_split` —
   and the artifact `config` block carries the same eleven (§ "Training",
   § "Python API"). Before building `TrainConfig`, read one shipped
   `checkpoint_info.json` and its exported `model_info.json` and confirm both
   `config` blocks hold these eleven keys. If one is missing, add it in the
   training or export code, with a test, and log it.

2. **`TrainResult` carries `early_stopped: bool`**, copied from the training
   loop's own flag. **Never derive it from `epochs_run < epochs_requested`**:
   each phase has its own early-stopping window, so a completed run whose
   Phase 1 stopped early ends short of `--epochs` with `early_stopped` false.
   Under `dry_run=True` it is `None`, like every other outcome field. Do not
   add a field for the "(N classes absent from test set)" count — fast-follow.

3. **`Classifier(checkpoint_path=…)` raises `OpticaValidationError`** both when
   the path does not exist and when it exists but is not a checkpoint folder
   containing `checkpoint_info.json`, a bare `.pt` file included. Construction
   checks existence only and never imports torch.

4. **Exporting an interrupted checkpoint** writes `epochs_trained` and
   `early_stopped` as `null` and warns. In the API that warning is a
   `WarningEntry` with its own `code`. Codes are stable API surface, so choose
   the name deliberately and log it.

5. **Declined prompts exit `3`; `click.Abort` means interrupted and exits
   `130`.** Every prompt this pass adds — `optica setup`, `optica run`'s R/C/S,
   any other — handles an `N` answer itself. Never `confirm(..., abort=True)`.
   At pass close, `findstr /s /n /c:"abort=True" src\*.py` must return nothing;
   record that in `notes/build-log.md`.

6. **The blocklist definition prompt.** `optica.run()` and `optica.fetch()`
   raise `OpticaValidationError` at the definition step, naming the blocklisted
   class and saying a concrete definition is required — never prompting. The
   CLI pauses where a prompt can fire, even under `--yes`, and raises where
   none can.

7. **Check, and fix if needed:** when `curate` or `clip` aborts on zero
   readable images it reports a **count only**. Reasons are listed only for
   user-provided files. If the shipped abort lists reasons for auto-fetched
   files, change it and log it.

8. **Not in V1:** `--only` is a fast-follow flag. Do not implement it.

Items 1–4 are public API surface. If this pass does not act on them, V1 ships
them as they are, and an exception class or a warning code cannot be changed
afterwards without breaking callers.
