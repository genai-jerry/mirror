# Deploying the backend

This guide sets up the backend's deployment from GitHub Actions and walks you
through the first deploy. It covers every secret and variable the deployment
and the backend read, how to prepare a Linux server, and how to check that the
backend is healthy afterwards.

The workflow is `.github/workflows/backend-deploy.yml` ("Backend deploy" in the
Actions tab). The server runs `deploy/compose.yaml` with Docker Compose, started
by `deploy/remote-deploy.sh`.

## 1. What deploys where

| Branch | GitHub Environment | Server |
|---|---|---|
| `staging` | `staging` | the staging server |
| `main` | `production` | the production server |

No other branch deploys, and a pull request never deploys.

**What starts a deploy.** A push to `staging` or `main` that changes at least
one of these:

- anything under `backend/`
- anything under `deploy/`
- `.github/workflows/backend-deploy.yml`

A push that changes only documents (`docs/`, `openspec/`), the Android app or
the factory's own files deploys nothing.

**Starting one by hand.** Open Actions → **Backend deploy** → **Run workflow**,
pick `staging` or `main` in the branch list, and press **Run workflow**. The run
deploys that branch's current commit to that branch's server. Any other branch
fails at once with `Manual deploys run only from staging or main`, and no
server is contacted.

**What one run does.**

1. Builds the image from `backend/Dockerfile` and publishes it to GitHub
   Container Registry as `ghcr.io/<owner>/mirror-backend:<commit>`. If the
   build fails, the run stops here and the server keeps its old version.
2. Checks that every required secret is set. If one is missing, the run fails
   and names it, before it contacts the server.
3. Connects to the server over SSH, copies `compose.yaml` and
   `remote-deploy.sh` into the deploy directory, and writes the backend's
   settings into a `.env` file there that only the deploy user can read.
4. Pulls the new image, replaces the old backend container, and checks
   `http://127.0.0.1:8000/healthz` on the server for up to 90 seconds.
5. On success, the run's summary says `Deployed <image> to <environment>`.
   On failure, it says `Deploy of <image> to <environment> failed` and shows
   the backend's last 50 log lines.

Two deploys to the same environment never run at the same time: the second
waits for the first to finish.

## 2. Secrets and variables

Set these in **Settings → Environments → `staging`** and again in
**Settings → Environments → `production`**, with each server's own values.
Every name belongs to both environments. There are no repository-wide
secrets to set.

| Name | Kind | Environment | Required | What it is for |
|---|---|---|---|---|
| `DEPLOY_HOST` | secret | `staging` and `production` | required | The server's address: a host name or an IP address. |
| `DEPLOY_USER` | secret | `staging` and `production` | required | The Linux user the deploy logs in as. |
| `DEPLOY_SSH_KEY` | secret | `staging` and `production` | required | The private SSH key for that user (the whole file, including the `BEGIN` and `END` lines). |
| `DEPLOY_KNOWN_HOSTS` | secret | `staging` and `production` | required | The server's identity, from `ssh-keyscan`. The deploy refuses to connect to a server that does not match it. |
| `DEPLOY_PORT` | secret | `staging` and `production` | optional, default `22` | The server's SSH port. |
| `SARVAM_API_KEY` | secret | `staging` and `production` | required | The Sarvam API key. Without it every text recognition and translation fails. |
| `ADMIN_TOKEN` | secret | `staging` and `production` | optional, default unset | Turns on the backend's admin configuration endpoints, and is the token they require. Unset means the admin endpoints do not exist. |
| `APP_TOKEN` | secret | `staging` and `production` | optional, default unset | Makes the backend require this token on every request from the app. Unset means the app needs no token. |
| `DEPLOY_DIR` | variable | `staging` and `production` | optional, default `/opt/mirror` | The directory on the server that holds `compose.yaml`, `remote-deploy.sh` and the `.env` file. |

Notes:

- `SARVAM_API_KEY`, `ADMIN_TOKEN` and `APP_TOKEN` must be one line with no
  single quote (`'`) in them. The deploy refuses a value that has either,
  because it would break the `.env` file on the server.
- The registry login uses the run's own short-lived token. You do not create
  a registry password or a `GITHUB_TOKEN` secret.
- `BACKEND_CONFIG_DIR` is set inside the image. Do not set it.
- Never put a real value from this table in a file in the repository, an
  issue or a pull request.

## 3. Preparing a server

You need a Linux server you can log in to as an administrator (with `sudo`).
The examples use `staging.example.com`; use your own server's address.

1. **Install Docker Engine and the Docker Compose plugin.** Follow Docker's
   instructions for your Linux distribution
   (<https://docs.docker.com/engine/install/>). Check both work:

   ```sh
   docker --version
   docker compose version
   ```

2. **Install `curl` and `bash`.** Most distributions have them already. On
   Debian or Ubuntu:

   ```sh
   sudo apt-get install -y curl bash
   ```

3. **Create the deploy user and let it run Docker.** The user name `deploy` is
   an example; whatever you choose goes into `DEPLOY_USER`.

   ```sh
   sudo adduser --disabled-password --gecos "" deploy
   sudo usermod -aG docker deploy
   ```

4. **Create the deploy directory, owned by that user.** Use the default
   `/opt/mirror`, or another path that you then put in `DEPLOY_DIR`.

   ```sh
   sudo mkdir -p /opt/mirror
   sudo chown deploy:deploy /opt/mirror
   ```

5. **Open port 8000 to the app.** The backend listens on plain HTTP on port
   8000. Opening that port in the server's firewall, or your cloud provider's
   firewall, is your job; the deploy does not change it. The health check runs
   on the server itself, so a closed port does not fail the deploy, but the app
   cannot reach the backend until it is open.

## 4. The SSH key

Do this on your own computer, not on the server. Make one key per environment.

1. **Create the key** (no passphrase, because the deploy runs unattended):

   ```sh
   ssh-keygen -t ed25519 -N "" -C "mirror-deploy-staging" -f mirror-deploy
   ```

   This writes two files: `mirror-deploy` (private) and `mirror-deploy.pub`
   (public).

2. **Authorise the key on the server.** Add the line in `mirror-deploy.pub` to
   the deploy user's `~/.ssh/authorized_keys`:

   ```sh
   sudo mkdir -p /home/deploy/.ssh
   echo "<the line from mirror-deploy.pub>" | sudo tee -a /home/deploy/.ssh/authorized_keys
   sudo chown -R deploy:deploy /home/deploy/.ssh
   sudo chmod 700 /home/deploy/.ssh
   sudo chmod 600 /home/deploy/.ssh/authorized_keys
   ```

3. **Check the key works** from your computer:

   ```sh
   ssh -i mirror-deploy -p 22 deploy@staging.example.com docker ps
   ```

   It must log in without a password and list containers (an empty list is
   fine). If `docker ps` says "permission denied", log out of the server
   completely and back in, or reboot, so the `docker` group takes effect.

4. **Record the server's identity:**

   ```sh
   ssh-keyscan -p 22 staging.example.com
   ```

   Use the same address and port you will put in `DEPLOY_HOST` and
   `DEPLOY_PORT`. Check the output matches the server's real host key before
   you trust it.

5. **Store the values** in the environment (next section):
   - the whole content of `mirror-deploy` → `DEPLOY_SSH_KEY`;
   - the whole output of `ssh-keyscan` → `DEPLOY_KNOWN_HOSTS`.

   Then delete `mirror-deploy` from your computer, or keep it in a password
   manager. Never commit it.

## 5. Creating the environments

1. Open the repository on GitHub → **Settings → Environments**.
2. Press **New environment**, name it exactly `staging`, and press
   **Configure environment**.
3. Under **Environment secrets**, add each secret from section 2 with the
   staging server's values. Leave out the optional ones you do not need.
4. Under **Environment variables**, add `DEPLOY_DIR` only if you did not use
   `/opt/mirror`.
5. Repeat for an environment named exactly `production`, with the production
   server's values. You can also add **Required reviewers** to `production` so
   every production deploy waits for a person's approval.

## 6. The first deploy

The factory cannot run Docker, so a person runs the first deploy and checks it.

1. Make sure the backend (`backend/Dockerfile`) is on the branch you deploy.
   If it is not, the run fails at "Backend present" with
   `backend/Dockerfile is not on <branch>` and contacts no server.
2. Open Actions → **Backend deploy** → **Run workflow**, choose `staging`, and
   press **Run workflow**.
3. Wait for both jobs to go green. The run's summary says
   `Deployed ghcr.io/<owner>/mirror-backend:<commit> to staging`.
4. Confirm it with the health check, from your computer:

   ```sh
   curl http://staging.example.com:8000/healthz
   ```

   The answer must be `{"status":"ok"}` (spaces may differ). If this times out
   but the run was green, port 8000 is closed: see step 5 of section 3. You can
   also check on the server itself:

   ```sh
   curl http://127.0.0.1:8000/healthz
   ```

5. Do the same for `production` once you are ready to deploy `main`.

**If the run fails:**

| The run says | What to do |
|---|---|
| `Secret <NAME> is not set in the <environment> environment` | Add that secret to that environment (section 5) and run again. |
| `... contains a quote or a line break` | Fix that secret's value (section 2, notes). |
| `Host key verification failed` | `DEPLOY_KNOWN_HOSTS` does not match the server. Run `ssh-keyscan` again (section 4, step 4). |
| `Permission denied (publickey)` | The key is not in the deploy user's `authorized_keys`, or `DEPLOY_USER` is wrong (section 4, step 2). |
| `permission denied ... docker.sock` | The deploy user is not in the `docker` group (section 3, step 3). |
| `mkdir: cannot create directory` or `scp: ... Permission denied` | The deploy directory is missing or not owned by the deploy user (section 3, step 4). |
| `Backend did not answer healthy within 90s` | Read the backend's log lines below the message. A missing or wrong `SARVAM_API_KEY` is the usual cause. |

## 7. Rolling back, and what the factory cannot check

**Rolling back.** There is no automatic rollback. To go back to an earlier
version, open the last successful run of **Backend deploy** for that
environment and press **Re-run all jobs**. It rebuilds and redeploys that run's
commit. The backend's runtime configuration (admin overrides) lives on a Docker
volume and survives every redeploy.

**Stopping the backend.** On the server, in the deploy directory:

```sh
docker compose -p mirror down
```

The runtime configuration volume stays unless you add `-v`.

**What the factory cannot check.** The factory's own runs cannot start Docker
or reach a server. They check the workflow and the scripts, but the first real
deploy to each server must be run by a person, following section 6.
