# mirror
Android app for real-time camera-based text translation using Sarvam OCR and translate

The product has two halves in this one repository (design decision D1):

| Folder | What it is |
|---|---|
| `backend/` | The translate proxy service — Python 3.12, FastAPI. It holds the Sarvam key, the rate budget and the translation cache. |
| `app/` | The Android app — Kotlin, Jetpack Compose, CameraX. Added by the app scaffold task. |
| `Makefile` | `test`, `build` and `lint` for both halves. |

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

From the repository root, `make test`, `make lint` and `make build` run the
same commands. The factory's runners call them directly, because `make` is not
installed there.

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
| `backend/config/defaults/budget.json` | The shipped per-minute recognition and translation budgets. |

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

With `APP_TOKEN` set, `GET /v1/languages` needs
`Authorization: Bearer $APP_TOKEN` as well.

## The factory

This repository is built by the Software Factory. `FACTORY.md` in the factory
plugin is the handbook; `openspec/changes/` holds each epic's proposal, specs,
design and tasks; `.factory/profile.json` tells the factory's roles this
repository's stack and commands.
