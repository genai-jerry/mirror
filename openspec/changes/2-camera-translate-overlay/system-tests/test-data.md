# System test data — camera translate overlay

Epic: genai-jerry/mirror#2. Four synthetic sets, used by the cases in
`test-plan.md`. The records are the files under `system-tests/data/` — all
synthetic: no production data, no personal data, no credentials. The Sarvam
API key is environment configuration, never test data.

## Loading

The repo has no `test_data` block in `.factory/profile.json` yet — this is
the first epic, and there is no loader to run. The test data loader task
(`tasks.md` § Task 11, issue #15) builds it: a `load` command that applies
the backend configuration sets (DS-2, DS-3) from this epic's data directory
(`openspec/changes/2-camera-translate-overlay/system-tests/data`, the last
argument) into a running backend, and an `unload` command that removes them
and restores the shipped configuration, both idempotent. That task fills in
this section with the two exact commands in the same PR.

DS-1 and DS-4 are tester-side materials used straight from the checkout:
nothing loads them into an environment.

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
- Setup: the `## Loading` command, naming the set to apply — `baseline`
  (Malayalam → English, Sarvam for both steps), `add-tamil` (adds Tamil as
  a source language), or `provider-change` (maps Malayalam translation to
  the alternate configured provider entry). The records carry the facts;
  the loader task maps them onto the configuration shape the language
  configuration task defines.
- Teardown: the `## Loading` unload command, which restores the shipped
  configuration.

The alternate provider entry in `provider-change` may point at the same
Sarvam account under a distinct configured name — what ST-8 verifies is
that the backend uses the entry the configuration names, observable in the
backend log, not that a second real vendor exists.

### DS-3: Low recognition budget configuration

- Used by: ST-6
- Records: `system-tests/data/DS-3.json`
- Setup: the `## Loading` command, applying a shared recognition budget of
  2 requests per minute — low enough that the app's own refresh cadence
  exhausts it inside a minute, without hammering Sarvam's real limits.
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
