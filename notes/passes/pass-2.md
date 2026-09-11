# Pass 2 — Input and acquisition

## Read
`spec/optica-plan-v1-core.md` § "Input & Acquisition" in full. Re-read
§ "Configuration" for anything the fetch path reads from config.
Also `notes/verified.md` — Task 3 settled the Open Images column schema.

## Build
`src/optica/input/`, everything except `clip.py`: local ingestion, the fetch
adapters, class-name rules and the blocklist, manifest handling, validation,
the `dataset/` conflict behaviour, and sessions.

Plus the mirroring test files. The plan states expected values for the
class-name rules and the `_x` collision sequence — transcribe them into stubs
as you go.

## Out of scope
`input/clip.py` (pass 4). The browser UI (pass 3). Anything under `training/`
or `export/`.

## No Flickr key
`.env` is empty — there is no `FLICKR_API_KEY`, and obtaining one now requires a
paid Flickr Pro subscription. Two consequences:

- Meet the milestone via local input or Open Images. Open Images needs no key:
  its per-image fetches resolve to `staticflickr.com` CDN URLs, which are plain
  HTTP GETs rather than API calls.
- The Flickr adapter will be written but never exercised end to end. Record that
  in `notes/build-log.md` alongside the MPS path, so it is not later mistaken for
  tested code.

Build and test the no-key path as the normal case, because it is.

## Where to run
Run the fetch end to end inside `.smoke/`, never at the repo root.

## Done when
`optica fetch` runs end to end and produces a manifest.
