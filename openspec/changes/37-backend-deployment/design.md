# Design — backend deployment

Epic: genai-jerry/mirror#37. Repo: `genai-jerry/mirror` only. Change folder:
`openspec/changes/37-backend-deployment/`.

This epic adds deployment files and a guide. It changes no backend code and
no Android code. It is written against the backend as it stands on the mirror
v1 epic branch (`factory/epic-2`): `backend/Dockerfile` (build context
`backend/`, port 8000, runtime configuration in `BACKEND_CONFIG_DIR`, which the
image sets to `/var/lib/mirror/runtime-config`), `GET /healthz` answering
`{"status": "ok"}` with no authentication, and `app/settings.py` reading exactly
four environment variables: `SARVAM_API_KEY`, `ADMIN_TOKEN`, `APP_TOKEN` and
`BACKEND_CONFIG_DIR`.

## Decisions

### D1 — One workflow file runs the whole deploy: a build job, then a deploy job

Why: the spec needs "build and publish, and only then connect to the server". Two
jobs in one file, with the deploy job waiting on the build job, give that order
for free, and one run in the Actions tab tells the whole story of one deploy.

The file is `.github/workflows/backend-deploy.yml`. The build-and-publish task
creates it with the triggers and the `build` job; the deploy task adds the
`deploy` job to the same file.

### D2 — A deploy starts only on a push to `staging` or `main` that touches the backend or the deployment files, or by hand

Why: the spec maps exactly two branches to servers, and a push that changes only
documents, the Android app or the factory's files must deploy nothing.

The trigger is `push` with `branches: [staging, main]` and a `paths` list:
`backend/**`, `deploy/**` and `.github/workflows/backend-deploy.yml`. Anything
outside that list (`openspec/**`, `docs/**`, `app/**`, `.github/factory-*`,
`.claude/**`, `.factory/**`) deploys nothing. There is no `pull_request`
trigger, so a pull request never deploys.

### D3 — A manual run uses GitHub's own branch picker, and refuses any branch but `staging` and `main`

Why: "Run workflow" already asks which branch to run from, and the run then uses
that branch's current commit, which is what the spec's manual run asks for. A
second branch input would be a second answer to the same question.

The trigger is `workflow_dispatch` with no inputs. The `build` job's first step
fails with `::error::Manual deploys run only from staging or main` when
`github.ref_name` is anything else, so no image is built and no server is
contacted.

### D4 — `staging` deploys to the GitHub Environment `staging`; `main` deploys to `production`

Why: each environment holds its own server address, login and backend secrets,
so the two servers can never share a value by accident, and a person can add a
required reviewer to `production` later without touching the workflow.

The deploy job sets
`environment: ${{ github.ref_name == 'main' && 'production' || 'staging' }}`.
Only the deploy job names an environment. The build job needs no secret beyond
the run's own token.

### D5 — The image goes to GitHub Container Registry, tagged with the full commit identifier

Why: the tag ties a running backend to exactly one commit, and redeploying an
older commit means re-running that commit's workflow run. The registry needs no
extra account, because the run's own token can publish to it.

The image name is `ghcr.io/<owner>/mirror-backend`, with the owner lower-cased
in the build step. The tag is `${{ github.sha }}`. No moving tag such as
`latest` is pushed, so a server never pulls anything but the exact tag it was
told to.

### D6 — The server pulls the image with the run's short-lived token, then logs out

Why: no long-lived registry password ever sits on the server or in a secret.
The run's token stops working when the run ends.

The deploy job has `packages: read`. On the server, the deploy script runs
`docker login ghcr.io --password-stdin` with that token fed through standard
input, pulls the image, and runs `docker logout ghcr.io` whatever the outcome.
The token never appears on a command line.

### D7 — The server's address, user, port and SSH key are environment secrets, and the server's identity is checked against a known-hosts secret

Why: the spec puts each server's login in secrets. Checking the server's host
key stops a run from handing the backend's secrets to a machine that only
pretends to be the server.

| Name | Kind | Required | Meaning |
|---|---|---|---|
| `DEPLOY_HOST` | secret | yes | The server's address (name or IP) |
| `DEPLOY_USER` | secret | yes | The Linux user the run logs in as |
| `DEPLOY_SSH_KEY` | secret | yes | The private SSH key for that user |
| `DEPLOY_KNOWN_HOSTS` | secret | yes | The server's line(s) from `ssh-keyscan`, so its identity is checked |
| `DEPLOY_PORT` | secret | no (22) | The SSH port |

`DEPLOY_PORT` is optional because almost every server listens on 22. A person
who wants fewer secrets to set can ask to drop `DEPLOY_KNOWN_HOSTS`; the run
would then trust whatever answers at the address.

### D8 — The backend's settings are environment secrets; the only variable is where the files live on the server

Why: `SARVAM_API_KEY`, `ADMIN_TOKEN` and `APP_TOKEN` are the only settings the
backend reads apart from its configuration directory, which the image fixes.
Inventing more variables would document settings nothing reads.

| Name | Kind | Required | Meaning |
|---|---|---|---|
| `SARVAM_API_KEY` | secret | yes | Sarvam key; without it every recognition fails |
| `ADMIN_TOKEN` | secret | no | Turns on the admin configuration endpoints |
| `APP_TOKEN` | secret | no | Makes the app send a token on every request |
| `DEPLOY_DIR` | variable | no (`/opt/mirror`) | The directory on the server holding the Compose file and its `.env` |

The setup guide's table is this table plus the secrets in D7, and nothing else.

### D9 — The secrets reach the server as a `.env` file only its owner can read

Why: Docker Compose reads the `.env` file in its own directory, and a file
written through standard input never puts a secret on a command line or in the
log. The file must stay on the server so the container comes back with its
settings after a server reboot.

The deploy job writes `SARVAM_API_KEY`, `ADMIN_TOKEN`, `APP_TOKEN` and
`BACKEND_IMAGE` (the image and tag) into `$DEPLOY_DIR/.env` through
`ssh … 'umask 077; cat > "$DEPLOY_DIR/.env"'`, fed from standard input. The
file is mode 600. The runner never writes the values to its own disk.

### D10 — The server runs one backend container through Docker Compose, with its configuration directory on a named volume

Why: Compose gives "replace the old container, keep the volume" in one
command, and a named volume survives every recreate of the container. The
spec asks for exactly one instance, because the backend's cache and rate
budget belong to one process.

`deploy/compose.yaml`, project name fixed as `mirror` (`name: mirror` at the top
of the file), so every deploy on a server addresses the same project. One
service, `backend`, with no `replicas` and no `container_name`.

### D11 — The backend is served on plain port 8000 on every interface

Why: the spec (interpretation 4) has no domain, HTTPS or reverse proxy. The
admin endpoints stay protected by `ADMIN_TOKEN`, and they do not exist at all
when that secret is unset.

### D12 — The health check runs on the server, against `127.0.0.1:8000/healthz`, for up to 90 seconds

Why: checking from the server itself proves the backend started, whatever the
server's firewall says about port 8000. It is the same check the repo profile
already names. 90 seconds covers a cold start on a small server.

The deploy script polls every 3 seconds with `curl -fsS`. It counts healthy
only when the answer is `{"status":"ok"}`. Opening port 8000 to the app is the
server owner's job, and the guide says so.

### D13 — Deploys to one environment queue behind each other; they are never cancelled

Why: cancelling a deploy halfway can leave the server between two versions.
Queueing keeps one deploy at a time, as the spec asks.

The deploy job sets
`concurrency: { group: backend-deploy-<environment>, cancel-in-progress: false }`.
GitHub keeps one waiting run per group: if a third push arrives while one runs
and one waits, the newest replaces the waiting one. The newest commit is still
what ends up deployed.

### D14 — Rollback is a person re-running an earlier successful run

Why: the proposal rules out automatic rollback. Re-running an older run rebuilds
and redeploys that run's commit, with the same tag, using the deploy job as it
was at that commit.

### D15 — Workflow syntax is checked with `actionlint` and shell with `bash -n`; nothing in the factory can run Docker

Why: Docker is not installed on the factory's runners and this branch has no
test suite. Static checks are what a factory run can prove. The first real
deploy is a person's, as the proposal says.

## Task 1 — Compose file that runs the backend on the server (#39)

Depends on nothing.

**Builds:** `deploy/compose.yaml`.

```yaml
name: mirror
services:
  backend:
    image: ${BACKEND_IMAGE:?BACKEND_IMAGE is not set}
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      SARVAM_API_KEY: ${SARVAM_API_KEY:?SARVAM_API_KEY is not set}
      ADMIN_TOKEN: ${ADMIN_TOKEN:-}
      APP_TOKEN: ${APP_TOKEN:-}
    volumes:
      - runtime-config:/var/lib/mirror/runtime-config
volumes:
  runtime-config:
```

(Illustrative; the task writes the real file.)

- `BACKEND_CONFIG_DIR` is **not** set here. The image already sets it to
  `/var/lib/mirror/runtime-config`, and the volume mounts at that same path.
  Repeating it here would create two places to change.
- `ADMIN_TOKEN` and `APP_TOKEN` default to empty. The backend treats an empty
  value as unset (`settings._env` strips it), so the admin endpoints and the
  app-token check stay off unless the secret is set.
- `:?` makes `docker compose` refuse to start with a clear message if the image
  or the Sarvam key is missing, as a second line of defence behind the deploy
  job's own check.
- No server address, port mapping beyond 8000, or secret value appears in the
  file.
- The container runs as root, as the image does today, so the named volume is
  writable with no ownership step.

**Checks the task runs:** parse the file as YAML
(`python3 -c 'import sys, yaml; yaml.safe_load(open(sys.argv[1]))' deploy/compose.yaml`).
`docker compose config` is the real check, and a person runs it (no Docker here).

**Scenarios:** Settings reach the container (the wiring), Redeploy keeps
configuration (the named volume survives `up -d` recreating the container).

## Task 2 — Workflow that builds and publishes the backend image (#40)

Depends on nothing.

**Builds:** `.github/workflows/backend-deploy.yml` with the triggers and the
`build` job.

- `on`: `push` to `[staging, main]` with the `paths` list in D2, and
  `workflow_dispatch` with no inputs (D3).
- Top-level `permissions: { contents: read }`. The `build` job raises it to
  `packages: write`.
- `build` job on `ubuntu-latest`, steps in order:
  1. **Guard** (D3): fail unless `github.ref_name` is `staging` or `main`.
  2. `actions/checkout@v4`.
  3. **Backend present:** fail with
     `::error::backend/Dockerfile is not on <branch>; the mirror v1 backend must reach this branch first`
     when the file is missing. Until mirror v1 lands, this is the message a
     person sees, not a confusing build error.
  4. Lower-case the owner and set the output `image=ghcr.io/<owner>/mirror-backend:<sha>`.
  5. `docker/setup-buildx-action@v3`, then `docker/login-action@v3` to
     `ghcr.io` with `github.actor` and `secrets.GITHUB_TOKEN`.
  6. `docker/build-push-action@v6` with `context: backend`,
     `file: backend/Dockerfile`, `push: true`, `tags:` the image output, and
     the GitHub Actions cache (`cache-from: type=gha`, `cache-to: type=gha,mode=max`).
- The job exposes `outputs.image`, which the deploy job reads.

A failed step fails the run. The deploy job (the deploy task) `needs: build`, so
no server is contacted after a failed build, and the server keeps its old
version. Until the deploy task lands, the workflow builds and publishes only.

The image holds only what is in `backend/`, copied by the Dockerfile. No secret
is a build argument, so no secret can end up in an image layer.

**Checks the task runs:** `actionlint` on the workflow (download its release
binary into the run's temp directory; if the network refuses, parse the file as
YAML and say so in the PR).

**Scenarios:** Other branches and pull requests, Documents-only push, Manual
run (the trigger), Image published before deploy, Build fails.

## Task 3 — Deploy job that ships the image to the branch's server and checks its health (#41)

Depends on the Compose file task and the build-and-publish workflow task.

**Builds:** the `deploy` job in `.github/workflows/backend-deploy.yml`, and
`deploy/remote-deploy.sh`, the script the job runs on the server.

`deploy` job:

- `needs: build`, `environment` as in D4, `concurrency` as in D13,
  `permissions: { contents: read, packages: read }`.
- `env` maps every secret and variable in D7 and D8 into the step that uses it.
  Never `set -x`; never `echo` a secret. GitHub masks secret values in the log;
  the job does not rely on that alone.

Steps, in order:

1. **Required settings present.** One shell step checks `DEPLOY_HOST`,
   `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS` and `SARVAM_API_KEY`.
   For each empty one it prints
   `::error::Secret <NAME> is not set in the <environment> environment`, then
   fails after checking all of them, so one run names every missing secret. No
   SSH has happened yet.
2. `actions/checkout@v4` (for `deploy/`).
3. **SSH set-up.** Write `DEPLOY_SSH_KEY` to `~/.ssh/deploy_key` (mode 600) and
   `DEPLOY_KNOWN_HOSTS` to `~/.ssh/known_hosts`. Every `ssh` and `scp` uses
   `-i ~/.ssh/deploy_key -p "${DEPLOY_PORT:-22}" -o StrictHostKeyChecking=yes -o BatchMode=yes`.
4. **Copy files.** `ssh … mkdir -p "$DEPLOY_DIR"`, then `scp` `deploy/compose.yaml`
   and `deploy/remote-deploy.sh` into it. `DEPLOY_DIR` defaults to `/opt/mirror`.
5. **Write `.env`** (D9): `printf` the four lines into
   `ssh … 'umask 077; cat > "<dir>/.env"'`. `BACKEND_IMAGE` is the build job's
   `image` output.
6. **Deploy.** `ssh … bash "<dir>/remote-deploy.sh" "<dir>"`, with the run's
   token on standard input (D6).
7. **Summary.** On success, append to `$GITHUB_STEP_SUMMARY`:
   `Deployed <image> to <environment>`, naming the environment and the tag.
   The host is a secret and is not printed. With `if: failure()`, a step appends
   `Deploy of <image> to <environment> failed` and prints the same as
   `::error::`.
8. **Clean-up**, `if: always()`: remove `~/.ssh/deploy_key`.

`deploy/remote-deploy.sh <dir>` (bash, `set -euo pipefail`, no `-x`):

1. `cd "$1"`.
2. Read the token from standard input; `docker login ghcr.io -u <actor> --password-stdin`.
   A `trap` runs `docker logout ghcr.io` on exit.
3. `docker compose pull backend`.
4. `docker compose up -d --remove-orphans backend`. Compose recreates the
   container when the image changed and leaves the named volume alone.
5. Check exactly one backend container runs:
   `docker compose ps -q backend | wc -l` must be 1, else fail.
6. Poll `curl -fsS http://127.0.0.1:8000/healthz` every 3 seconds for up to 90
   (D12). Healthy when the body contains `"status":"ok"`. On time-out, print the
   last 50 lines of `docker compose logs backend` and exit non-zero. The
   backend never logs its secrets (repo convention), so these lines are safe to
   show.

**Failure modes and edge cases**

| Scenario | What happens |
|---|---|
| Missing secret / Required key missing | Step 1 fails, naming each missing secret. No SSH. |
| Build fails | `needs: build` skips this job. |
| Changing a server | Only `DEPLOY_HOST` (and `DEPLOY_KNOWN_HOSTS`) change; no file does. |
| Host key changed or wrong | `StrictHostKeyChecking=yes` refuses; the run fails before any file is copied. |
| Server unreachable | `ssh` times out (`-o ConnectTimeout=20`); the run fails. |
| Registry pull refused | `docker compose pull` fails; the old container keeps running. |
| Unhealthy deploy | Poll times out; the run fails, naming environment and tag, with the backend's last log lines. The new, unhealthy container stays; a person re-runs an earlier run (D14). |
| Two pushes in quick succession | `concurrency` queues the second (D13). |
| Redeploy | `up -d` replaces the container; the volume keeps the overrides. |

**Checks the task runs:** `actionlint` on the workflow, `bash -n` and
`shellcheck` (if available) on `deploy/remote-deploy.sh`.

**Scenarios:** Push to staging, Push to main, Manual run (the deploy),
Changing a server, Missing secret, Required key missing, Settings reach the
container, Secrets stay out of sight, Redeploy keeps configuration, Redeploy
replaces the old container, Healthy deploy, Unhealthy deploy, Two pushes in
quick succession.

## Task 4 — Setup guide for the deployment (#42)

Depends on the deploy job task.

**Builds:** `docs/deployment.md`, and one line in `README.md` linking to it.

Sections:

1. **What deploys where.** `staging` → the staging server, `main` → the
   production server; which file changes start a deploy (D2); how to start one
   by hand (D3).
2. **Secrets and variables.** One table: name, kind (secret or variable),
   environment (`staging`, `production`, or both), required or optional with
   its default, and purpose. Exactly the names in D7 and D8. The task checks
   every `secrets.` and `vars.` name in the workflow appears in the table, and
   no other.
3. **Preparing a server.** Linux with Docker Engine and the Compose plugin,
   and `curl`. A deploy user in the `docker` group. `DEPLOY_DIR` created and
   owned by that user. Port 8000 open to the app.
4. **The SSH key.** `ssh-keygen -t ed25519 -N "" -f mirror-deploy`; add the
   `.pub` line to the deploy user's `~/.ssh/authorized_keys`; paste the private
   key into `DEPLOY_SSH_KEY`; run `ssh-keyscan -p <port> <host>` and paste the
   output into `DEPLOY_KNOWN_HOSTS`.
5. **Creating the environments.** Settings → Environments → `staging` and
   `production`, and the secrets in each.
6. **The first deploy.** Actions → "Backend deploy" → Run workflow → choose
   the branch. Confirm with `curl http://<host>:8000/healthz` answering
   `{"status":"ok"}`.
7. **Rollback** (D14), and **what the factory cannot check**: the first deploy
   must be run by a person.

No real host, key or token appears in the guide; examples use
`staging.example.com` and placeholders.

**Scenarios:** Complete list of secrets and variables, Preparing a server.

## Rollout order

1. The Compose file and the build-and-publish workflow, in either order, then
   the deploy job, then the guide, all onto `factory/epic-37`. Nothing runs on
   the epic branch, because the workflow fires only on `staging` and `main`.
2. **Before gate GS:** a person creates the `staging` environment and its
   secrets from the guide. The epic's merge onto `staging` touches
   `.github/workflows/backend-deploy.yml`, so it starts a staging deploy at
   once.
3. If mirror v1 is not yet on `staging`, that first run fails at "Backend
   present" with a clear message and contacts no server. It is harmless; the
   next push after mirror v1 lands deploys.
4. **Before gate G3:** create the `production` environment. The promotion merge
   to `main` starts the production deploy.

## Rollback

- A bad backend version: re-run the last good run (D14).
- A bad deployment change: revert the change on `staging`; the revert touches
  `deploy/**` or the workflow, so it redeploys.
- Removing the whole epic: revert its integration merge. The server keeps
  running the last deployed container until a person stops it with
  `docker compose -p mirror down` (the volume stays unless `-v` is given).

## Open questions

1. **Where the test cases can run.** `.github/factory-testing.json` has
   `mode: gate` and no `run_on`, so the cases are meant to run on the epic
   branch before gate GS. This workflow deploys only from `staging` and `main`
   (the spec says so), and mirror v1's backend is not on either yet. So no
   case can run before GS, and gate mode holds GS until they pass. A person
   must choose before testing starts: comment `Skip tests` on the epic and run
   the cases on staging after GS, or set `"run_on": "staging"` in
   `.github/factory-testing.json` (that changes every epic in this repo).
   The design does not bend the spec's branch rule to fix this.
