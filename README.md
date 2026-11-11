# mirror
Android app for real-time camera-based text translation using Sarvam OCR and translate

The product has two halves in this one repository (design decision D1):

| Folder | What it is |
|---|---|
| `backend/` | The translate proxy service — Python 3.12, FastAPI. It holds the Sarvam key, the rate budget and the translation cache. |
| `app/` | The Android app — Kotlin, Jetpack Compose, CameraX. |
| `Makefile` | `test`, `build` and `lint` for both halves. |
| `scripts/gate.sh` | What those three actually run. The factory calls it directly. |

## Running the backend locally

You need [uv](https://docs.astral.sh/uv/) — nothing else is a prerequisite.
`backend/.python-version` pins Python 3.12, the version the service ships on,
and uv installs that interpreter itself if the machine has no matching one.

```bash
cd backend
uv sync                      # create .venv and install dependencies
uv run uvicorn app.main:app --reload --port 8000
curl http://127.0.0.1:8000/healthz     # {"status": "ok"}
```

Test, lint and build:

```bash
cd backend
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv build
```

## Building the app

You need a **JDK 21 or later** and an Android SDK with **platform 37.2** and
**build-tools 37.0.0**. The app's code targets JVM 17, but the unit suite runs
on Robolectric's Android 36 runtime, which refuses to start on a JDK 17
("Android SDK 36 requires Java 21"). Android Studio installs both; on a bare machine use
the SDK command-line tools and point `ANDROID_HOME` at the SDK (or write
`sdk.dir=/path/to/sdk` into `app/local.properties`). Gradle itself comes from
the wrapper, so there is nothing to install for it.

```bash
cd app
./gradlew testDevDebugUnitTest   # the unit suite — Robolectric, no device needed
./gradlew assembleDebug          # every flavour's debug APK
./gradlew lint                   # Android lint
```

The app is built in three flavours, which differ only in the backend they talk
to (design decision D5):

| Flavour | Backend |
|---|---|
| `dev` | `http://10.0.2.2:8000/` — the local backend, as the emulator sees the host machine |
| `systemTest` | `http://127.0.0.1:8000/` by default. Point it elsewhere with `-Pmirror.systemTestBackendUrl=http://host:8000/` |
| `staging` | The address in the `APP_BACKEND_URL` secret of the `staging` environment, which the "Staging app" workflow passes in. Its own app id (`com.genaijerry.mirror.staging`), named "Mirror staging" on the phone, signed with the test key, and a version that rises with every workflow run |

## Both halves at once

From the repository root, `make test`, `make lint` and `make build` run
`scripts/gate.sh`, which does the backend half and then the app half. The
factory's runners call `scripts/gate.sh` directly, because `make` is not
installed there.

The app half needs the Android SDK. Where there is none the gate says
`app: test SKIPPED` and passes on the backend result alone — so read the
output rather than only the exit code. `MIRROR_APP_GATE=required` turns that
skip into a failure, which is what a machine that is meant to have the SDK
should set.

## Deploying the backend

Deploying the backend: see the [setup guide](docs/deployment.md) for every secret and variable, preparing a server and the first deploy.

## Running the backend in Docker

```bash
docker build -f backend/Dockerfile -t mirror-backend backend
docker run --rm -p 8000:8000 \
  -e SARVAM_API_KEY=... \
  -e ADMIN_TOKEN=... \
  -v "$PWD/runtime-config:/var/lib/mirror/runtime-config" \
  mirror-backend
curl http://127.0.0.1:8000/healthz
```

This is how the system test environment's backend is stood up. Mount the
runtime configuration directory as shown, so configuration an operator or the
test data loader writes survives a restart of the container.

## Configuration

Two JSON files decide what the backend supports; the environment carries only
secrets and where things are (design decision D6).

| File | Holds |
|---|---|
| `backend/config/defaults/languages.json` | The shipped source and target languages, and the named provider entry that reads and translates each source language. |
| `backend/config/defaults/budget.json` | The shipped per-minute recognition and translation budgets, and how long a translation is kept in the cache (`translation_cache_seconds`, ten minutes; zero switches the cache off). |

An operator's change is a whole replacement file of the same name in the
override directory, so deleting it restores what the service shipped with. A
file is read again only when it has changed, so a change takes effect on the
next request and needs no restart.

| Variable | Meaning |
|---|---|
| `SARVAM_API_KEY` | The Sarvam subscription key. Never leaves the backend and appears in no log line or response. |
| `BACKEND_CONFIG_DIR` | The override directory. Default `./runtime-config`. |
| `ADMIN_TOKEN` | Set it to switch the admin configuration endpoints on. They do not exist without it. |
| `APP_TOKEN` | Optional. Set it to make the app send that token on every call (design decision D10). |

Make both tokens long and of plain ASCII characters. A token with an accent in
it is refused rather than accepted, because an HTTP header carries its bytes in
a different encoding from the one the environment gives the backend.

### Changing the configuration of a running backend

Three endpoints, all needing `Authorization: Bearer $ADMIN_TOKEN`, all safe to
repeat. A body is a whole configuration file, never a part of one; a file the
service could not use is refused with a message saying why, and nothing is
stored. This is also the surface the system test data loader calls.

```bash
# add a language, or point one at a different provider entry
curl -X PUT http://127.0.0.1:8000/v1/admin/config/languages \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  --data @my-languages.json

# lower the per-minute budgets
curl -X PUT http://127.0.0.1:8000/v1/admin/config/budget \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"recognition_per_minute": 2, "translation_per_minute": 60, "max_wait_seconds": 15}'

# put everything back to what the service shipped with
curl -X DELETE http://127.0.0.1:8000/v1/admin/config/overrides \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# what the app's picker shows — codes and names, and nothing else
curl http://127.0.0.1:8000/v1/languages
```

### Translating one frame

`POST /v1/frames/translate` is the one endpoint the app calls. It takes the
cropped image as a multipart file (PNG or JPEG, 5 MB at most) and the language
pair as fields, and answers with the text it read, that text's translation, and
where the text sits in the image as fractions of its width and height.

```bash
curl -X POST http://127.0.0.1:8000/v1/frames/translate \
  -F image=@crop.png -F source_language=ml-IN -F target_language=en-IN
```

```json
{
  "recognized_text": "…Malayalam text…",
  "translated_text": "…English text…",
  "region_hint": {"x": 0.08, "y": 0.41, "width": 0.84, "height": 0.17},
  "cached": false
}
```

`cached` says the translation came from the backend's cache rather than from
the provider. A frame with no text in it answers 200 with both texts empty and
`region_hint` null — the app draws nothing for it.

| Answer | What happened |
|---|---|
| 400 `unsupported_language` | The pair is not in the configuration. The message names the code. Nothing was sent to a provider. |
| 400 `invalid_request` | The body is not a frame to translate: no image, an empty one, a format that is not PNG or JPEG, or a missing language. |
| 413 `image_too_large` | The image is over 5 MB. |
| 429 `budget_exhausted` | The recognition allowance is used up and the wait ran out. `Retry-After` says when to come back. |
| 502 `provider_error` | Sarvam failed, or answered something the backend could not read. |
| 504 `recognition_timeout` | Sarvam's parse job did not finish in time. |

The image is never written to disk: it is in the request's memory and is
discarded with the response.

With `APP_TOKEN` set, `GET /v1/languages` and `POST /v1/frames/translate` both
need `Authorization: Bearer $APP_TOKEN`.

### The system test data loader

An epic's system test plan names configuration sets a tester needs in force
before a case can run — a language added, a provider changed, a recognition
budget of two calls a minute. `backend/scripts/test_data.py` puts them into a
running backend through the admin endpoints above, and takes them out again. It
reads the records from the epic's own data directory, which is the last
argument; `ADMIN_TOKEN` and `BACKEND_URL` say which backend to change.

```bash
export ADMIN_TOKEN=... BACKEND_URL=http://127.0.0.1:8000
DATA=openspec/changes/2-camera-translate-overlay/system-tests/data

# the state every case starts from: every override removed, baseline languages
uv run --project backend python backend/scripts/test_data.py load "$DATA"

# one named set, for the case in front of you
uv run --project backend python backend/scripts/test_data.py load --set low-budget "$DATA"

# the shipped configuration back
uv run --project backend python backend/scripts/test_data.py unload "$DATA"
```

A set replaces one whole configuration file, so running any of these twice
changes nothing the second time, and a set that governs the budget leaves the
languages alone. The names a `--set` takes are the record ids in the epic's
`system-tests/test-data.md`, which also lists the sets a tester uses straight
from the checkout — those load nowhere, and asking for one says so.

## The factory

This repository is built by the Software Factory. `FACTORY.md` in the factory
plugin is the handbook; `openspec/changes/` holds each epic's proposal, specs,
design and tasks; `.factory/profile.json` tells the factory's roles this
repository's stack and commands.
