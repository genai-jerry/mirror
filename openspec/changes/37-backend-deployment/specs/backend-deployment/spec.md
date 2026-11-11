## Purpose

Builds the backend into a Docker image and deploys it to a server per branch from GitHub Actions, so a release needs no hand-typed server commands and every secret and variable it needs is named in one place.

## ADDED Requirements

### Requirement: Branch-to-server mapping
The deployment SHALL deploy to the staging server when `staging` receives a push and to the production server when `main` receives a push, and SHALL deploy nothing for any other branch or for a pull request.

#### Scenario: Push to staging
- **WHEN** a commit that changes the backend is pushed to `staging`
- **THEN** the workflow deploys the new backend to the staging server and does not touch the production server

#### Scenario: Push to main
- **WHEN** a commit that changes the backend is pushed to `main`
- **THEN** the workflow deploys the new backend to the production server and does not touch the staging server

#### Scenario: Other branches and pull requests
- **WHEN** a commit is pushed to any other branch, or a pull request is opened or updated
- **THEN** no deploy runs and no server is contacted

### Requirement: Deploys only for backend changes
The deployment SHALL run only when a push changes the backend, the deployment files or the workflow itself, and SHALL be startable by hand for a chosen branch.

#### Scenario: Documents-only push
- **WHEN** a push to `staging` changes only files under `openspec/`, the Android app or the factory's own files
- **THEN** no deploy runs

#### Scenario: Manual run
- **WHEN** a person starts the workflow by hand and chooses `staging` or `main`
- **THEN** the workflow deploys that branch's current commit to that branch's server

### Requirement: Image build and publish
The deployment SHALL build the backend's Docker image from `backend/Dockerfile` with `backend/` as the build context, publish it to GitHub Container Registry tagged with the commit it was built from, and deploy that exact tag.

#### Scenario: Image published before deploy
- **WHEN** a deploy starts for a commit
- **THEN** the workflow builds the image, publishes it tagged with that commit's identifier, and only then connects to the server

#### Scenario: Build fails
- **WHEN** the image does not build
- **THEN** the run fails, the server is not contacted, and the server keeps running its previous version

### Requirement: Server address and login come from secrets
The deployment SHALL read each server's address, SSH user, SSH private key and SSH port from secrets held per environment (`staging` and `production`), and no server address or key SHALL appear in the repository.

#### Scenario: Changing a server
- **WHEN** an owner changes the staging server's address secret
- **THEN** the next staging deploy goes to the new address with no change to any file in the repository

#### Scenario: Missing secret
- **WHEN** a deploy starts and a required secret for its environment is not set
- **THEN** the run fails before contacting the server, and the failure message names the missing secret

### Requirement: Backend settings come from secrets and variables
The deployment SHALL give the running backend its `SARVAM_API_KEY`, `ADMIN_TOKEN` and `APP_TOKEN` from per-environment secrets and any non-secret settings from per-environment variables, and SHALL require `SARVAM_API_KEY` to be set.

#### Scenario: Settings reach the container
- **WHEN** a deploy completes for an environment whose secrets are set
- **THEN** the running backend has those values in its environment

#### Scenario: Required key missing
- **WHEN** a deploy starts and `SARVAM_API_KEY` is not set for its environment
- **THEN** the run fails before contacting the server and names `SARVAM_API_KEY`

#### Scenario: Secrets stay out of sight
- **WHEN** a deploy runs
- **THEN** no secret value appears in the workflow log, in the published image or in any file committed to the repository

### Requirement: Single instance with persistent runtime configuration
The deployment SHALL run exactly one backend container per server, and SHALL keep the backend's runtime-configuration directory on a volume that survives a container restart and a redeploy.

#### Scenario: Redeploy keeps configuration
- **WHEN** an operator has written a language override through the backend's admin endpoint and a new version is then deployed
- **THEN** the new backend still serves that override

#### Scenario: Redeploy replaces the old container
- **WHEN** a new version is deployed to a server that already runs the backend
- **THEN** the old container is replaced and only one backend container is running afterwards

### Requirement: Post-deploy health check
The deployment SHALL check the backend's `GET /healthz` endpoint on the target server after starting it, and SHALL fail the run if the endpoint does not report healthy within a set time.

#### Scenario: Healthy deploy
- **WHEN** the new backend starts and `/healthz` answers healthy
- **THEN** the run succeeds and its summary names the environment and the image tag deployed

#### Scenario: Unhealthy deploy
- **WHEN** the new backend does not answer `/healthz` as healthy within the set time
- **THEN** the run fails and its output says which environment and image tag failed

### Requirement: One deploy at a time per environment
The deployment SHALL NOT run two deploys to the same environment at once.

#### Scenario: Two pushes in quick succession
- **WHEN** a second push to `staging` arrives while a staging deploy is running
- **THEN** the second deploy waits for the first to finish rather than running alongside it

### Requirement: Setup guide
The repository SHALL contain a setup guide that lists every secret and variable the deployment and the backend read, and explains how to prepare a server and run the first deploy.

#### Scenario: Complete list of secrets and variables
- **WHEN** a person reads the setup guide
- **THEN** for every secret and variable it gives the name, the environment it belongs to, whether it is required, and what it is for

#### Scenario: Preparing a server
- **WHEN** a person has a new Linux server and follows the guide
- **THEN** the guide tells them what must be installed on it, how to create and authorise the SSH key, and how to run the first deploy by hand and confirm it with the health check
