# Backend deployment

## Why

The backend (the translate proxy service) can run in Docker, but nothing builds it, ships it or starts it on a server. Every deploy would be a person logging in and typing commands, with the server address and secrets living in someone's head. The owner wants the backend to deploy itself from GitHub Actions, with every secret and variable named and documented.

## What Changes

- Add a GitHub Actions workflow that builds the backend's Docker image, publishes it to GitHub Container Registry, and deploys it to a server over SSH.
- Map branches to servers: a push to `staging` deploys to the staging server, a push to `main` deploys to the production server. Each server's address and login come from secrets, so a host change is a secret change, not a code change.
- Add a Docker Compose file that runs the backend on the server as one instance, with its runtime-config directory kept on a volume.
- Check the backend's health endpoint after each deploy and fail the run if it does not answer.
- Add a setup guide that lists every secret and variable (name, which environment, required or optional, what it is for), how to prepare a server, and how to run the first deploy.

## Capabilities

### New Capabilities

- `backend-deployment`: building, publishing and deploying the backend image to a configured server per branch, with the secrets and variables it needs documented.

### Modified Capabilities

- None. `openspec/specs/` is empty on `main`; the backend's own requirements are in the mirror v1 epic and are not changed here.

## Impact

- **Repositories:** the `mirror` repo only. New files: a deploy workflow under `.github/workflows/`, a Compose file, and a setup guide. The backend code and its Dockerfile are not changed.
- **Depends on the mirror v1 epic.** The backend and `backend/Dockerfile` exist today only on the mirror v1 epic's branch, not on `main` or `staging`. This change is written against the Dockerfile's documented contract (build context `backend/`, port 8000, `GET /healthz`, runtime configuration in the directory named by `BACKEND_CONFIG_DIR`). Its first real deploy can only happen after mirror v1 reaches the branch being deployed.
- **Secrets and variables.** Two GitHub Environments, `staging` and `production`, each hold their own server address, SSH login and backend secrets. The backend's own settings are `SARVAM_API_KEY` (required), `ADMIN_TOKEN` and `APP_TOKEN` (optional). The setup guide is the complete list; no secret value appears in the repository, the image or a log.
- **Verification limit.** Docker is not installed on the factory's runners, so no factory run can build the image or run the workflow. A person must trigger the first deploy and confirm it. The workflow can be started by hand for that purpose.
- **Production gate.** The production deploy fires on a push to `main`. Every merge to `main` is a person's promotion merge (gate G3), so that merge is the production go-ahead.

## Non-goals

- No change to the backend code, its Dockerfile or its endpoints.
- No domain name, HTTPS or reverse proxy: the backend is reached on plain port 8000.
- No Kubernetes, no multiple replicas. The backend runs as one instance because its cache and rate budget are per-process.
- No automatic rollback. A person redeploys an earlier image by re-running the workflow.
- No Android app release, and no change to the backend address built into the app.
- No provisioning of the server itself (creating the machine, installing Docker). The guide says what the server needs.

## Interpretations taken

1. Two servers, one per branch: `staging` deploys to a staging server and `main` deploys to a production server, because the owner asked that the deploy host for each branch be configurable through secrets.
2. "Configurable through secrets" is read as the server address, SSH user, SSH key and port being GitHub Environment secrets, one set per environment.
3. The image is built in GitHub Actions and pushed to GitHub Container Registry, and the server pulls it, rather than building on the server (the default offered; no answer given).
4. The server is a Linux host with Docker and Docker Compose, reached over SSH, serving the backend on plain port 8000 with no domain or HTTPS (the default offered; no answer given).
5. This work builds on the mirror v1 epic's code without waiting for it to reach `main`: the epic branch is cut from `main` as the factory policy requires, the workflow is written against the Dockerfile's documented contract, and the first real deploy waits until mirror v1 is on the deployed branch (the default offered; no answer given).
6. A deploy runs only when the backend or the deployment files change. A push that touches only documents, the Android app or the factory's files deploys nothing.
7. "Make sure the deployment happens" is read as: the workflow checks the backend's health endpoint after deploying and fails visibly if it does not answer. It is not read as the factory itself running a deploy, which it cannot do without Docker.
