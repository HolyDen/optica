# Pass 3 — Browser

## Read
`spec/optica-plan-v1-core.md` § "Labeling & Curation" in full.
Also `notes/verified.md`, and `notes/build-log.md` from the pass 2 entries
onward — pass 2 built and exercised the label-from-manifest path this pass
depends on.

## Build
`src/optica/server/` — the FastAPI application, its routes, both pages, and the
shared JS and CSS. Vanilla front end; no build step.

Plus mirroring tests. Route-level tests belong in `tests/integration/`.

## Out of scope
`training/`, `export/`, `api/`, `cli/setup.py`. Any change to `input/` beyond
what the two pages genuinely require — if something in `input/` looks wrong,
log it rather than fixing it here.

## Done when
`optica label` and `optica curate` both start, serve their page, and write back
through their session files.
