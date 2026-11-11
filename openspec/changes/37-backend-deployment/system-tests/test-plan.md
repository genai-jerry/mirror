# System test plan — backend deployment

Epic: genai-jerry/mirror#37. Black-box: derived from `proposal.md`, `specs/` and `tasks.md`.

## Scope

These cases prove, on real servers, what the automated suite cannot: that a change
reaches the right server, that settings and secrets behave, and that the guide
works for a person. Every scenario in `specs/backend-deployment/spec.md` has a
case. No scenario is left to the automated suite, because none can run a
deploy: Docker is not installed on the factory's runners.

Prerequisites for every case: the mirror v1 backend (with `backend/Dockerfile`)
is on the branch being deployed, and a staging server and a production-style
server exist (see ST-12). Run the cases on the staging server unless a case
says otherwise. Use a throwaway test server in place of production for ST-2.

## Environment

The cases run as the code assembles on the epic branch. The tester needs: the
GitHub repository (Actions and Settings → Environments), a staging server, a
production-style test server, and a terminal that can reach each server over SSH
and on port 8000.

## Test cases

### ST-1: Staging branch update deploys to the staging server
- Covers: backend-deployment/Branch-to-server mapping/Push to staging; backend-deployment/Post-deploy health check/Healthy deploy; backend-deployment/Image build and publish/Image published before deploy
- Depends on: Task 1, Task 2, Task 3
- Data: none
- Execution: manual
- Preconditions: staging environment secrets are set; the staging server is prepared.
- Steps:
  1. Commit a small backend change to `staging`.
  2. Watch the workflow run in GitHub Actions.
  3. After it ends, open `http://<staging server>:8000/healthz`.
  4. Check the production server's container start time.
- Expected: The run builds and publishes the image, then deploys, and succeeds. Its summary names the `staging` environment and the commit tag. The image in GitHub Container Registry carries that commit's identifier. `/healthz` on staging reports healthy. The production server was not touched.

### ST-2: Main branch update deploys to the production server
- Covers: backend-deployment/Branch-to-server mapping/Push to main
- Depends on: Task 1, Task 2, Task 3
- Data: none
- Execution: manual
- Preconditions: `production` environment secrets are set (pointing at a test server).
- Steps:
  1. Merge a promotion change that touches the backend into `main`.
  2. Watch the run. Then check `/healthz` on the production server and the staging server's container start time.
- Expected: The run deploys to the production server only and succeeds with `production` named in the summary. The staging server is unchanged.

### ST-3: Other branches, pull requests and non-backend changes deploy nothing
- Covers: backend-deployment/Branch-to-server mapping/Other branches and pull requests; backend-deployment/Deploys only for backend changes/Documents-only push
- Depends on: Task 2
- Data: none
- Execution: manual
- Preconditions: none.
- Steps:
  1. Commit a backend change to a feature branch. Open a pull request from it.
  2. Commit a change that touches only a file under `openspec/` to `staging`.
  3. Commit a change that touches only the Android app to `staging`.
  4. Check the Actions tab and the staging server's container start time after each.
- Expected: No deploy run starts for the feature branch, the pull request or the two non-backend changes. No server is contacted. The container start time does not change.

### ST-4: Manual run deploys the chosen branch
- Covers: backend-deployment/Deploys only for backend changes/Manual run
- Depends on: Task 2, Task 3
- Data: none
- Execution: manual
- Preconditions: none.
- Steps:
  1. In Actions, start the workflow by hand and choose `staging`.
  2. Watch the run and check staging `/healthz`.
  3. Start it again, choosing `main`, against the test production server.
- Expected: Each run deploys that branch's current commit to that branch's server only, and succeeds.

### ST-5: A failed image build contacts no server
- Covers: backend-deployment/Image build and publish/Build fails
- Depends on: Task 2
- Data: none
- Execution: manual
- Preconditions: staging runs a healthy backend. Note its container start time.
- Steps:
  1. Commit a change to `staging` that breaks the image build (for example, an invalid line in the Dockerfile).
  2. Watch the run.
  3. Check staging `/healthz` and the container start time.
  4. Revert the breaking change.
- Expected: The run fails at the build step. No SSH connection is made. The staging server still runs the previous version and answers healthy.

### ST-6: Changing a server secret moves the next deploy
- Covers: backend-deployment/Server address and login come from secrets/Changing a server
- Depends on: Task 3
- Data: none
- Execution: manual
- Preconditions: a second prepared server is available.
- Steps:
  1. Change the staging host secret to the second server's address.
  2. Commit a backend change to `staging`.
  3. Check both servers.
- Expected: The deploy goes to the second server and no file in the repository changed. The first server is untouched.

### ST-7: A missing secret stops the run before the server is contacted
- Covers: backend-deployment/Server address and login come from secrets/Missing secret; backend-deployment/Backend settings come from secrets and variables/Required key missing
- Depends on: Task 3
- Data: none
- Execution: manual
- Preconditions: note the staging container start time.
- Steps:
  1. Delete the staging SSH key secret. Start a manual run on `staging`. Restore the secret.
  2. Delete the staging `SARVAM_API_KEY` secret. Start a manual run. Restore the secret.
  3. Read each failure message and check the server's start time.
- Expected: Both runs fail before any server contact. Each message names the missing secret (the SSH key secret, then `SARVAM_API_KEY`). The server is unchanged.

### ST-8: Settings reach the backend and secrets stay out of sight
- Covers: backend-deployment/Backend settings come from secrets and variables/Settings reach the container; backend-deployment/Backend settings come from secrets and variables/Secrets stay out of sight
- Depends on: Task 1, Task 3
- Data: none
- Execution: manual
- Preconditions: staging has `SARVAM_API_KEY`, `ADMIN_TOKEN` and `APP_TOKEN` set to test values.
- Steps:
  1. Deploy to staging.
  2. Call an admin endpoint with the `ADMIN_TOKEN` value, then with a wrong token.
  3. Call a protected app endpoint with `APP_TOKEN`, then without it.
  4. Read the full workflow log and search it for each secret value.
  5. Search the committed files for the values.
- Expected: The right token is accepted and the wrong one is refused, which shows the values reached the container. No secret value appears in the log, in the image or in any committed file.

### ST-9: A redeploy keeps configuration and leaves one container
- Covers: backend-deployment/Single instance with persistent runtime configuration/Redeploy keeps configuration; backend-deployment/Single instance with persistent runtime configuration/Redeploy replaces the old container
- Depends on: Task 1, Task 3
- Data: none
- Execution: manual
- Preconditions: staging runs the backend.
- Steps:
  1. Write a language override through the backend's admin endpoint. Confirm it is served.
  2. Commit a backend change to `staging` and wait for the deploy.
  3. Request the override again.
  4. On the server, list the running backend containers.
- Expected: The override is still served. Exactly one backend container runs, and it is the new one.

### ST-10: An unhealthy backend fails the run
- Covers: backend-deployment/Post-deploy health check/Unhealthy deploy
- Depends on: Task 3
- Data: none
- Execution: manual
- Preconditions: none.
- Steps:
  1. Commit a backend change to `staging` that makes the backend start but never answer `/healthz` as healthy.
  2. Watch the run.
  3. Revert the change.
- Expected: The run fails after waiting a set time. The output names the `staging` environment and the image tag that failed.

### ST-11: Two quick changes deploy one after the other
- Covers: backend-deployment/One deploy at a time per environment/Two pushes in quick succession
- Depends on: Task 3
- Data: none
- Execution: manual
- Preconditions: none.
- Steps:
  1. Commit a backend change to `staging`.
  2. While its deploy is running, commit a second change to `staging`.
  3. Watch both runs.
- Expected: The second deploy waits until the first finishes. The two deploy steps never run at the same time.

### ST-12: A new person follows the setup guide to a first deploy
- Covers: backend-deployment/Setup guide/Complete list of secrets and variables; backend-deployment/Setup guide/Preparing a server
- Depends on: Task 4
- Data: none
- Execution: manual
- Preconditions: a new Linux server, and someone who has not seen the workflow.
- Steps:
  1. Read the guide's list of secrets and variables. Compare it with the names the workflow and Compose file read.
  2. Follow the guide to prepare the server and to create and authorise the SSH key.
  3. Set the secrets as the guide says and run the first deploy by hand.
  4. Confirm it with the health check the guide names.
- Expected: Every secret and variable the workflow reads is listed with name, environment, required or optional, and purpose. The guide names what to install and how to authorise the key. Following it alone ends in a healthy backend.

## Traceability

| Scenario | Cases |
|---|---|
| Push to staging | ST-1 |
| Push to main | ST-2 |
| Other branches and pull requests | ST-3 |
| Documents-only push | ST-3 |
| Manual run | ST-4 |
| Image published before deploy | ST-1 |
| Build fails | ST-5 |
| Changing a server | ST-6 |
| Missing secret | ST-7 |
| Settings reach the container | ST-8 |
| Required key missing | ST-7 |
| Secrets stay out of sight | ST-8 |
| Redeploy keeps configuration | ST-9 |
| Redeploy replaces the old container | ST-9 |
| Healthy deploy | ST-1 |
| Unhealthy deploy | ST-10 |
| Two pushes in quick succession | ST-11 |
| Complete list of secrets and variables | ST-12 |
| Preparing a server | ST-12 |
