# System test data — camera translate overlay

Epic: genai-jerry/mirror#2. Four synthetic sets, used by the cases in
`test-plan.md`. The records are the files under `system-tests/data/` — all
synthetic: no production data, no personal data, no credentials. The Sarvam
API key is environment configuration, never test data.

## Loading

The two commands, run from the repository root. They are the `test_data`
block in `.factory/profile.json`, with this epic's data directory as their
last argument:

```bash
export ADMIN_TOKEN=...                      # the token the backend was started with
export BACKEND_URL=http://127.0.0.1:8000    # where that backend runs

# the state every case starts from: nothing left over, baseline languages
uv run --project backend python backend/scripts/test_data.py load \
  openspec/changes/2-camera-translate-overlay/system-tests/data

# put the shipped configuration back
uv run --project backend python backend/scripts/test_data.py unload \
  openspec/changes/2-camera-translate-overlay/system-tests/data
```

One case at a time needs one named set. Add `--set <name>` to the load
command — `baseline`, `add-tamil`, `provider-change` or `low-budget`:

```bash
uv run --project backend python backend/scripts/test_data.py load --set low-budget \
  openspec/changes/2-camera-translate-overlay/system-tests/data
```

A named set replaces the one configuration file it governs and leaves the
other alone, so lowering the budget for ST-6 keeps the languages a tester
set for ST-7. Every command is safe to repeat: a set is a whole
configuration file that replaces the file of the same name, so a second run
writes the same thing rather than stacking a second copy. `unload` with
nothing loaded says so and succeeds.

The loader reaches the backend over HTTP, through the admin configuration
endpoints, so the backend may be anywhere `BACKEND_URL` points. It must have
been started with `ADMIN_TOKEN` set, or those endpoints do not exist and the
loader says so.

DS-1 and DS-4 are tester-side materials used straight from the checkout:
nothing loads them into an environment, and asking the loader for one of
their records tells you that.

### DS-1: Malayalam display headlines

- Used by: ST-1, ST-2, ST-3, ST-4, ST-5, ST-6, ST-8, ST-10
- Records: `system-tests/data/DS-1.json`
- Setup: open the file and display one headline's `text_ml` at a time,
  full-screen at a large font size on a second screen, in good light,
  camera roughly square-on. Each record carries a `reference_en` the tester
  compares the overlay's meaning against.
- Teardown: none — nothing is loaded anywhere.

Three synthetic news-style headlines (H1–H3), invented for this plan. H3 is
reserved for ST-8 so its text is guaranteed not to be in the cache when the
provider-change case needs a fresh translation.

### DS-2: Language configuration sets

- Used by: ST-7, ST-8
- Records: `system-tests/data/DS-2.json`
- Setup: the `## Loading` load command with `--set` naming the set to apply
  — `baseline` (Malayalam → English, Sarvam for both steps), `add-tamil`
  (adds Tamil as a source language), or `provider-change` (maps Malayalam
  translation to the alternate configured provider entry). The records carry
  the facts; the loader maps them onto the languages file's shape, taking the
  provider entries and the display names from the shipped configuration.
- Teardown: the `## Loading` unload command, which restores the shipped
  configuration.

The alternate provider entry in `provider-change` may point at the same
Sarvam account under a distinct configured name — what ST-8 verifies is
that the backend uses the entry the configuration names, observable in the
backend log, not that a second real vendor exists.

### DS-3: Low recognition budget configuration

- Used by: ST-6
- Records: `system-tests/data/DS-3.json`
- Setup: the `## Loading` load command with `--set low-budget`, applying a
  shared recognition budget of 2 requests per minute — low enough that the
  app's own refresh cadence exhausts it inside a minute, without hammering
  Sarvam's real limits. The wait deadline and the cache's lifetime stay as
  the service ships them.
- Teardown: the `## Loading` unload command, restoring the configured
  production budget.

### DS-4: Endpoint request sample

- Used by: ST-9
- Records: `system-tests/data/DS-4.json`
- Setup: decode the embedded `png_base64` to a PNG file as the record's
  `how_to_use` says, and send it to the frame translation endpoint with the
  `unsupported_request` parameters (source `fr-FR`). The image is a tiny
  blank PNG: the request must be rejected on the language, before any
  provider sees the image, so its content does not matter.
- Teardown: none — nothing is loaded anywhere.
