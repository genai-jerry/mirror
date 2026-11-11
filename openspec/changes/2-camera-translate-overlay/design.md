# Design — camera translate overlay

Epic: genai-jerry/mirror#2. This repository is new and empty, so this design
chooses the stack as well as the shape of the change (the repo profile says
"Not chosen yet"); gate G2 approves both together. It covers every task in
`tasks.md`, the API between the app and the backend, and how the system test
plan's cases and data (`system-tests/`) become runnable.

## Decisions

### D1 — The backend and the Android app live in this one repository, side by side

`backend/` holds the proxy service, `app/` holds the Android app, and a
`Makefile` at the root runs test, build and lint for both. Why: the epic is
one product with two halves that change together; one repository keeps one
pipeline, one epic branch and one promotion. The alternative — a second
repository for the app — adds cross-repo ceremony with no second team to
justify it.

### D2 — The backend is Python with FastAPI

Python 3.12, FastAPI on uvicorn, httpx for outgoing calls, pytest for tests,
ruff for lint, dependencies in `pyproject.toml` installed with `uv`. Why:
the backend's whole job is waiting on Sarvam (submit, poll, download), and
FastAPI's async model does that cheaply; pytest with respx makes the Sarvam
calls easy to fake in tests. Rejected: Node/Express (equally capable, but
Python keeps the option of reusing Sarvam's official Python client), and Go
(faster to run, slower to write, and speed is not the constraint — Sarvam's
latency is).

### D3 — The Android app is Kotlin with Jetpack Compose and CameraX

Kotlin 2.x, Jetpack Compose for the UI, CameraX for the camera view and
frame capture, OkHttp/Retrofit for backend calls, Gradle (Kotlin DSL), JUnit
with Robolectric for unit tests. Why: this is the current first-party
Android stack — best documentation, best camera support, longest support
horizon. Rejected: Flutter/React Native (cross-platform buys nothing — iOS
is a stated non-goal) and the older View/XML stack (no advantage for a new
app).

### D4 — The phone finds where text is; Sarvam reads what it says

The app uses Google's free on-device ML Kit text recognizer only to locate
text regions in the camera view and track where they sit on screen. It
ignores ML Kit's reading of the text — Malayalam goes to Sarvam. Why: an
on-device detector is the only way to crop tightly and anchor the overlay
without a network call per video frame. Risk, named in the proposal: ML
Kit's ability to *locate* Malayalam script is unproven, so when it finds no
region for two cycles in a row the app falls back to sending the centre of
the frame — the feature keeps working, just with a looser crop.

### D5 — The app calls one backend endpoint, sending the cropped photo as a file upload

`POST /v1/frames/translate` takes the cropped image plus the source and
target language, and answers with the recognized text, its translation and
a region hint. Why: one endpoint keeps the API key, the budget, the cache
and the provider choice in one place, and a file upload (multipart) avoids
base64 inflation on a mobile connection.

### D6 — Languages, providers and budgets are JSON files the backend re-reads while running

The shipped configuration lives in `backend/config/defaults/`; an operator's
changes are override files in a runtime directory, written through a
token-protected admin endpoint and re-read on change — no restart, no app
release. Why: the spec requires adding a language or switching a provider
with no app release, and the system tests load and unload configuration
against a *running* backend (DS-2, DS-3). Rejected: a database for
configuration — two files do not justify one.

### D7 — The translation cache is backend memory with a time limit

Cache entries are keyed by a hash of the recognized text plus the language
pair and provider entry, kept for a configurable lifetime (default 10
minutes), in process memory. Why: the cache only has to answer "the same
headline seen again" within a session; memory is free and empties itself.
Consequence, stated plainly: the backend runs as **one instance** in v1 —
the cache and the budget (D8) are per-process. Scaling out would move both
to Redis; that is a later change, not this one.

### D8 — The recognition budget is a per-minute counter with a wait queue

A sliding one-minute window counts outgoing recognition calls across all
users; a request past the budget waits its turn up to a configurable
deadline (default 15 seconds), and past that the app is told to retry later
(HTTP 429). The per-minute values live in configuration (D6) because they
are plan-dependent. Why: the spec says defer, never exceed; a queue with a
deadline defers without stacking unbounded work, and the app's overlay
behaviour (keep the last good one) makes a 429 invisible to the person.

### D9 — The app refreshes about every 5 seconds, by itself

A new cycle starts when the previous one finishes or fails, never more than
one in flight, with at least 5 seconds (configurable) between starts. Why:
inside the ~10-second experience the proposal asks for, slow enough that
one phone cannot drain the shared budget, and simple to reason about. The
cadence is a constant in the app's build configuration for v1.

### D10 — No sign-in in v1; an optional app token can be switched on

The frame endpoint is open by default; setting `APP_TOKEN` in the backend's
environment makes it require that token in a header, and the app ships with
the token in its build configuration when one is set. Why: there are no
user accounts in scope, but an open proxy spends Sarvam credit, so
operators get a switch that costs nothing to leave off in development. A
token inside an installed app is a deterrent, not a secret — stated here so
the approver knows what it is and is not.

## Repository layout

```
backend/            FastAPI service (pyproject.toml, app/, tests/, config/defaults/, scripts/)
app/                Android app (Gradle Kotlin DSL, app module, unit tests)
Makefile            test / build / lint for both halves
openspec/           this change folder
```

No database anywhere in this epic: there is no migration plan because there
is nothing to migrate. Persistent state is exactly two kinds of file —
shipped configuration in git, and runtime overrides in the backend's
configuration directory. Camera images are never written to disk; they are
processed in memory and discarded with the response.

## API contract — app ↔ backend

All responses are JSON. Errors use one shape:
`{"error": {"code": "<machine_code>", "message": "<plain sentence>"}}`.

### `GET /healthz`
200 `{"status": "ok"}`. No auth. Used by the factory's health checks.

### `GET /v1/languages`
Returns what the picker shows, straight from configuration:

```json
{
  "sources": [{"code": "ml-IN", "name": "Malayalam"}],
  "targets": [{"code": "en-IN", "name": "English"}]
}
```

200 always (an empty configuration returns empty lists). Auth: app token
when enabled (D10).

### `POST /v1/frames/translate`
Multipart form: `image` (PNG or JPEG, 5 MB cap → 413 over it),
`source_language` and `target_language` (BCP-47, e.g. `ml-IN`, `en-IN`).
Auth: app token when enabled (D10).

- **400 `unsupported_language`** — the pair is not in configuration. The
  message names the offending code ("source language fr-FR is not
  configured"). Checked **before** any budget or provider work: ST-9
  requires no provider call for a rejected request.
- **429 `budget_exhausted`** — the recognition budget's wait deadline
  passed (D8). Carries `Retry-After` in seconds.
- **504 `recognition_timeout`** — Sarvam's parse job did not finish inside
  the backend's recognition timeout.
- **502 `provider_error`** — Sarvam answered with a failure.
- **200** —

```json
{
  "recognized_text": "…Malayalam text…",
  "translated_text": "…English text…",
  "region_hint": {"x": 0.08, "y": 0.41, "width": 0.84, "height": 0.17},
  "cached": false
}
```

`region_hint` is the union of the recognized text blocks' bounding boxes,
normalised 0–1 against the uploaded image, or `null` when no text was
recognized — in which case both text fields are `""`, the call still
returns 200, and no translation call was made (ST-10's blank wall).

### Admin endpoints (operators and the test data loader)
Enabled only when `ADMIN_TOKEN` is set in the backend environment;
`Authorization: Bearer <ADMIN_TOKEN>`; 401 without it, 404 when disabled.

- `PUT /v1/admin/config/languages` — body is a whole languages file (shape
  below); written as the override, takes effect on the next request.
  Idempotent: same body, same result.
- `PUT /v1/admin/config/budget` — same, for the budget file.
- `DELETE /v1/admin/config/overrides` — removes every override and
  restores the shipped configuration. Idempotent.

## Configuration shape

`backend/config/defaults/languages.json` (shipped; overrides use the same
shape):

```json
{
  "sources": [
    {"code": "ml-IN", "name": "Malayalam",
     "recognition_provider": "sarvam-parse",
     "translation_provider": "sarvam-translate"}
  ],
  "targets": [{"code": "en-IN", "name": "English"}],
  "providers": {
    "sarvam-parse":        {"kind": "sarvam_parse"},
    "sarvam-translate":    {"kind": "sarvam_translate", "model": "mayura:v1"},
    "sarvam-translate-alt": {"kind": "sarvam_translate", "model": "sarvam-translate:v1"}
  }
}
```

Provider entries have **names**, and every provider call is logged with the
entry name it used — that is what ST-8 observes when the configuration
remaps Malayalam translation to `sarvam-translate-alt`. The alternate entry
points at the same Sarvam account through a different model, which is
exactly the "distinct configured name" DS-2 describes.

`backend/config/defaults/budget.json`:

```json
{"recognition_per_minute": 60, "translation_per_minute": 30, "max_wait_seconds": 15}
```

The backend re-reads configuration when the files change (modification-time
check per request — cheap, and no restart). Environment variables carry
only secrets and deployment facts: `SARVAM_API_KEY`, `ADMIN_TOKEN`,
`APP_TOKEN` (optional), `BACKEND_CONFIG_DIR` (override directory, default
`./runtime-config`).

## Contract with Sarvam (backend side only)

Verified against docs.sarvam.ai on 2026-11-09:

- **Recognition** — `POST https://api.sarvam.ai/doc-ai/v1/job/parse`,
  multipart `file` (our PNG/JPEG crop), `language` (the configured source
  code), `output_format=json`; then poll
  `GET /doc-ai/v1/job/<id>/status` every second until a terminal status;
  then fetch `GET /doc-ai/v1/job/<id>/download-url` and read the ZIP's JSON,
  which carries text blocks **with bounding boxes** — the source of our
  region hint. Backend recognition timeout: 12 seconds, configurable.
  Auth header: `api-subscription-key`.
- **Translation** — `POST https://api.sarvam.ai/translate`, JSON
  `{input, source_language_code, target_language_code, model}`;
  synchronous; `mayura:v1` caps input at 1,000 characters, so recognized
  text is truncated there with a warning log (headlines are far shorter).

The parse flow is asynchronous and tuned for documents; whether a single
small crop completes inside the ~10-second experience is the proposal's
open risk. The 1-second poll and the 12-second timeout are this design's
answer; the spike the proposal calls for measures the real latency and may
retune both numbers (configuration, not code).

## Logged events (the system test plan reads these)

One structured line per event, written to standard output, each carrying a
UTC timestamp and the request id:

| Event | When | Carries |
|---|---|---|
| `request.rejected` | 400/401/413/429 | the error code and, for languages, the offending code |
| `recognition.call` | a parse job is submitted | provider entry name, job id |
| `recognition.deferred` | the budget queue holds a request | current wait depth |
| `translation.call` | a translate request goes out | provider entry name |
| `translation.cache_hit` | the cache answers | — |

ST-5, ST-6, ST-8 and ST-9 are verdicts read from exactly these lines; they
are part of the contract, not decoration.

## Task designs

### Task 1 — Backend scaffold (#4)

Builds: the `backend/` project as D2 chooses it — FastAPI app factory,
`GET /healthz`, structured logging set up, configuration loader reading
`config/defaults/` with the override directory resolved from
`BACKEND_CONFIG_DIR`, one passing test (health endpoint via FastAPI's test
client), a `Dockerfile` (python slim, uvicorn) and a README section saying
how to run it locally and in Docker — that README is how the system test
environment's backend gets stood up. Creates the root `Makefile` with
`test` / `build` / `lint` targets covering the backend
(`uv run pytest`, `uv build` or a docker build, `uv run ruff check`).
In the same PR, per the repo's gotcha: set `stack`, `commands` (each one a
command this task ran) and `conventions` in `.factory/profile.json`.
Depends on: nothing.

### Task 2 — Language configuration and the languages endpoint (#5)

Builds: the configuration shape above, the shipped
`config/defaults/languages.json` (Malayalam → English, Sarvam entries), the
mtime-checked re-reader, the admin endpoints (languages, budget, overrides —
all three live here so the loader task has one surface to call), and
`GET /v1/languages`. Tests prove: the endpoint mirrors the file; an override
written through the admin endpoint changes the answer with no restart;
deleting overrides restores the shipped list; admin calls without the token
are refused. Depends on: the backend scaffold.

### Task 3 — Sarvam recognition client (#6)

Builds: `backend/app/providers/sarvam_parse.py` — submit the crop, poll,
download, unzip, parse the JSON blocks into `(text, bounding boxes)`,
normalise the union box 0–1, map Sarvam's terminal failure states onto the
`provider_error` shape, enforce the 12-second timeout. Reads
`SARVAM_API_KEY` from the environment only. Logs `recognition.call`. Tests
fake Sarvam with respx (submit → pending → completed → ZIP fixture) and
cover timeout and failure states; no live Sarvam call in the suite.
Depends on: the backend scaffold.

### Task 4 — Translation client with the translation cache (#7)

Builds: `backend/app/providers/sarvam_translate.py` (synchronous translate
call, model from the provider entry, 1,000-character truncation) and the
in-memory cache (D7): key = SHA-256 of whitespace-normalised recognized
text + source + target + provider entry name; value = translation +
expiry; lifetime from configuration (default 10 minutes). The provider
entry is resolved from configuration **per call**, so a provider change
takes effect on the next request (ST-8). Logs `translation.call` /
`translation.cache_hit`. Tests prove: second identical text makes no
provider call; different provider entry misses the cache; expiry evicts
(clock faked — the test plan leaves timing to this suite). Depends on: the
language configuration and languages endpoint.

### Task 5 — Shared recognition rate budget (#8)

Builds: `backend/app/budget.py` — one process-wide async limiter: a
sliding one-minute window over recognition calls, an acquire that waits in
FIFO order up to `max_wait_seconds`, then raises the 429 shape; values
re-read from configuration so DS-3's "2 per minute" takes effect while
running. Logs `recognition.deferred` with queue depth. Tests prove: the
third call in a 2/minute window waits; the deadline raises; a changed
budget file changes the limit without restart; concurrent acquires never
exceed the window (the multi-user concurrency the system test plan left to
this suite). Depends on: the Sarvam recognition client (it wraps that
client's call path).

### Task 6 — Frame translation endpoint (#9)

Builds: `POST /v1/frames/translate` wiring the pipeline in this order:
app-token check (D10) → language-pair validation against configuration
(400 before anything else — ST-9) → size cap → budget acquire → recognition
→ empty-text short-circuit (200 with empty fields, no translation) → cache
lookup → translation → response. Images live only in request memory.
Tests cover every status code in the contract above end to end with faked
providers, including "rejected request makes no provider call" and "cache
hit makes no translate call". Depends on: the Sarvam recognition client,
the translation client with the translation cache, and the shared
recognition rate budget.

### Task 7 — App scaffold with the live camera screen (#10)

Builds: the `app/` project as D3 chooses it — single-activity Compose app,
CameraX preview filling the screen, camera permission flow (ask once,
settings pointer on denial), backend base URL in `BuildConfig` per build
flavour (dev → local backend, the system test build points at the test
environment), one passing unit test (Robolectric smoke test of the main
screen). Extends the root `Makefile` so `test` / `build` / `lint` also run
`./gradlew testDebugUnitTest`, `./gradlew assembleDebug`, `./gradlew lint`,
and extends `commands` in `.factory/profile.json` the same way — noting in
the profile's gotchas that building the app needs the Android SDK on the
machine. Depends on: the backend scaffold (the two scaffolds edit the
profile in turn, not at once).

### Task 8 — Text-region detection with automatic refresh (#11)

Builds: the ML Kit analyzer on CameraX's analysis stream (D4) — locate text
blocks, keep the current anchor region updated at analysis rate so the
overlay tracks the text between refreshes; and the refresh loop (D9) — at
most one cycle in flight, ≥5 seconds between starts, each cycle cropping
the anchor region (centre-of-frame fallback after two empty detections)
with padding, downscaling to ≤1280 px long edge, JPEG ~80, and handing the
crop plus its screen rectangle to a `FrameTranslator` interface this task
defines and fakes in tests. Tests prove the loop's discipline (never
overlapping, cadence respected, fallback engages) with a faked clock and
faked detector. Depends on: the app scaffold with the live camera screen.

### Task 9 — Translated overlay anchored to the text (#12)

Builds: the real `FrameTranslator` — an OkHttp/Retrofit client for
`POST /v1/frames/translate` (20-second request timeout, multipart as the
contract says) — and the Compose overlay: translated text drawn on a
readable backing at the screen position computed from the crop rectangle
plus the response's region hint, re-anchored by Task 8's tracking between
refreshes. State rule, the heart of the graceful-degradation scenarios:
the overlay holds the **last successful** translation through pending,
failed, timed-out and 429 cycles — never a blank, never an error state —
and an empty-text 200 (blank wall) clears it. Tests fake the backend and
prove each transition. Depends on: the frame translation endpoint and
text-region detection with automatic refresh.

### Task 10 — Language picker served by the backend (#13)

Builds: a picker sheet fed from `GET /v1/languages` at app start and on
open (no caching beyond the session — a configuration change shows up on
next open, which is what ST-7 exercises), persisting the chosen pair in
DataStore, defaulting to Malayalam → English, and feeding the pair into
every frame request. Tests fake the endpoint and prove: a language added
to the response appears; the persisted choice survives restart. Depends
on: the language configuration and languages endpoint, and the app
scaffold with the live camera screen.

### Task 11 — Test data loader (#15)

Builds: `backend/scripts/test_data.py`, run as

```
python backend/scripts/test_data.py load --set <baseline|add-tamil|provider-change|low-budget> <data-dir>
python backend/scripts/test_data.py unload <data-dir>
```

with the backend named by `BACKEND_URL` and authenticated by `ADMIN_TOKEN`
— it reaches the environment the test plan names because the admin
endpoints (Task 2) are HTTP, so "where the backend runs" is just a URL.
`load` reads DS-2/DS-3 records from the data directory (the last argument,
per the profile contract), maps them onto the configuration shape above,
and PUTs them; `unload` calls the overrides delete. Both are idempotent
because the admin surface is PUT/DELETE. DS-1 and DS-4 load nothing, as
`test-data.md` says. In the same PR: add the `test_data` block (`load`,
`unload`, `format: "json"`) to `.factory/profile.json` — each command one
this task ran against a locally running backend — and fill in the
`## Loading` section of `system-tests/test-data.md` with the exact
commands. Depends on: the language configuration and languages endpoint
(the admin surface), and the shared recognition rate budget (DS-3 must
have a budget to set).

## Failure modes, per spec scenario

| Scenario | Where handled | Behaviour |
|---|---|---|
| Text detected and translated | Tasks 6, 8, 9 | crop → recognize → translate → overlay at the hint position, inside one cycle |
| Overlay stays while refresh is pending | Task 9 | last-successful state held through a pending cycle |
| Headline changes | Tasks 8, 9 | next cycle's recognized text differs → cache miss → new translation replaces the overlay |
| Backend call times out | Task 9 | timeout/429/5xx all resolve a cycle as failed; overlay unchanged; next cycle retries |
| Successful translation request | Task 6 | the 200 contract above |
| Same headline seen again | Task 4 | cache hit, `cached: true`, no translate call |
| Rate budget exhausted | Task 5 | queue, then 429 with Retry-After; the provider's limit is never exceeded |
| Adding a new source language | Tasks 2, 10 | override file → `GET /v1/languages` → picker on next open |
| Provider changed for a language | Tasks 2, 4 | provider entry resolved per call; next uncached request uses the new entry |

Cross-cutting: a blank scene returns an empty 200 and draws nothing
(ST-10); oversized uploads die at 413 before the budget; the Sarvam key
appears in no log line and no response.

## Rollout order and rollback

Rollout is the dependency order in `tasks.md`: backend scaffold → languages
→ recognition client → translation+cache → budget → endpoint → app scaffold
→ detection/refresh → overlay → picker → loader. Every merge onto the epic
branch leaves it releasable: the backend is complete and testable before
the app consumes it, and nothing reaches staging until gate GS.

Rollback: nothing in this epic deploys anywhere until the integration merge,
so before GS a bad task is a revert on the epic branch; after it, the epic's
single integration merge commit is the one revert that demotes the whole
epic, exactly as the factory's branch policy provides. There is no database
and no migration, so no rollback step beyond git. Runtime configuration
overrides are removed with the admin delete (or by emptying the override
directory) — the shipped defaults are always the fallback.

## Cross-repo contract

None — this epic touches only this repository; the only API contract is the
app ↔ backend one above, and both halves ship from the same epic branch.
