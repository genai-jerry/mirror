# System test plan — installable staging Android app

Epic: genai-jerry/mirror#61. Task numbers refer to `tasks.md`.

## Scope

These cases prove, with a person and a real phone, that a change to the app on `staging` produces an installable signed app that talks to the staging backend, and that the owner and tester guides work.

Left to the automated suites (workflow tests and the app's unit tests), because a person cannot provoke them safely or see them:

- **App not on the branch yet** — the workflow tests prove the failure message. Once the app is on `staging`, no real commit exists without it.
- **Failed build publishes nothing** — the workflow tests prove the publish job needs the build job. Breaking the shared `staging` branch on purpose is not a test.
- **Any other plain HTTP server** and **Other builds unchanged** — the app's unit tests prove the allowed-address rule per build flavour. A tester cannot point the app at another server.

## Environment

Staging, after the release to staging (GS): the `staging` branch, the repository's Actions tab and Releases page, the staging backend, and an Android phone. The app must be on `staging` and the build secrets set (ST-13 sets them).

## Test cases

### ST-1: App change pushed to staging builds and publishes
Covers: staging-app-distribution/Build on app changes that reach staging/App change pushed to staging
Depends on: Task 1, Task 2
Data: none
Execution: manual
Preconditions: the secrets are set; the app is on `staging`.
Steps:
1. Commit a change to one file under `app/` on `staging`.
2. Open the Actions tab and watch the app build run.
3. Open the Releases page.
Expected: the build run starts on that commit and ends green. A new pre-release exists with one APK attached.

### ST-2: Commit that does not touch the app builds nothing
Covers: staging-app-distribution/Build on app changes that reach staging/Push that does not touch the app
Depends on: Task 1
Data: none
Execution: manual
Preconditions: as ST-1. Note the newest pre-release.
Steps:
1. Commit a change to `staging` that touches only a document, such as a README line.
2. Wait two minutes, then open the Actions tab and the Releases page.
Expected: no app build run starts for that commit, and no new pre-release exists.

### ST-3: Other branches and pull requests build nothing
Covers: staging-app-distribution/Build on app changes that reach staging/Other branches and pull requests
Depends on: Task 1
Data: none
Execution: manual
Preconditions: as ST-1.
Steps:
1. On a scratch branch, change a file under `app/` and send the branch to GitHub.
2. Open a pull request from it to `staging`, then add one more commit to it.
3. Wait two minutes, then open the Actions tab and the Releases page.
Expected: no app build run starts for the branch or the pull request, and no new pre-release exists. Close the pull request afterwards.

### ST-4: Manual run builds from the current staging commit
Covers: staging-app-distribution/Build on app changes that reach staging/Manual run
Depends on: Task 1, Task 2
Data: none
Execution: manual
Preconditions: as ST-1.
Steps:
1. In the Actions tab, start the app build by hand on `staging`.
2. Try to start it by hand on another branch, if the page offers that.
3. Open the Releases page.
Expected: the run on `staging` ends green and a new pre-release exists, naming `staging`'s current commit. A run on another branch does not publish a pre-release.

### ST-5: Pre-release is marked as a pre-release and not as latest
Covers: staging-app-distribution/Published as a GitHub pre-release/Pre-release created; staging-app-distribution/Published as a GitHub pre-release/Not marked as a production release
Depends on: Task 2
Data: none
Execution: manual
Preconditions: a pre-release from ST-1 or ST-4.
Steps:
1. Open the newest pre-release on the Releases page.
2. Read its notes and its attached files.
3. Open the repository's front page and read the "Releases" box on the right.
Expected: one APK is attached. The notes name the commit and the app version. GitHub shows the "Pre-release" badge. The front page's "Latest" release is not this one (or there is none).

### ST-6: Missing backend address secret stops the build
Covers: staging-app-distribution/Staging build talks to the staging backend/Missing backend secret
Depends on: Task 1
Data: none
Execution: manual
Preconditions: as ST-1. Note the newest pre-release. Do this when no other tester is waiting for a build.
Steps:
1. Delete the staging backend address secret.
2. Start the app build by hand on `staging`.
3. Read the run's log. Then set the secret again.
Expected: the run fails before any build step and names the missing secret. No new pre-release exists.

### ST-7: Missing signing secret stops the build
Covers: staging-app-distribution/Signed with one fixed test key/Missing signing secret
Depends on: Task 1
Data: none
Execution: manual
Preconditions: as ST-6.
Steps:
1. Delete one signing secret, such as the key password.
2. Start the app build by hand on `staging`.
3. Read the run's log. Then set the secret again.
Expected: the run fails before any build step and names the missing secret. No new pre-release exists.

### ST-8: Installed app reaches the staging backend
Covers: staging-app-distribution/Staging build talks to the staging backend/App reaches the staging backend; staging-app-distribution/Plain HTTP to the staging backend only/Plain HTTP staging backend
Depends on: Task 1, Task 2, Task 3, Task 4
Data: none
Execution: manual
Preconditions: a pre-release from the current secrets, installed on the phone as in ST-14. The staging backend is up and uses plain HTTP.
Steps:
1. Open the app and allow the camera.
2. Point the camera at a printed line of text in a supported language.
3. Choose a target language.
Expected: the app shows the translation of that text over the camera view. It shows no network or security error.

### ST-9: Changing the backend address needs no code change
Covers: staging-app-distribution/Staging build talks to the staging backend/Changing the staging backend
Depends on: Task 1, Task 3, Task 4
Data: none
Execution: manual
Preconditions: a second reachable backend address (a copy of staging, or the same backend by another name).
Steps:
1. Change the staging backend address secret to the second address.
2. Start the app build by hand on `staging`.
3. Install the new APK and repeat ST-8's steps.
4. Check that the run added no commit to the repository.
Expected: the new build translates through the second address, and the repository has no new commit from this change. Put the original address back afterwards.

### ST-10: App token is accepted by the staging backend
Covers: staging-app-distribution/Staging build talks to the staging backend/Token switch on
Depends on: Task 1, Task 3
Data: none
Execution: manual
Preconditions: the staging backend requires an app token and the matching secret is set.
Steps:
1. Install the newest staging build.
2. Repeat ST-8's steps.
3. Set the token secret to a wrong value, run the build by hand, install it, and repeat.
Expected: with the right token the translation shows. With the wrong token the backend refuses and the app shows its error state, not a translation. Put the right token back afterwards.

### ST-11: A newer build installs over an older one
Covers: staging-app-distribution/Signed with one fixed test key/New build installs over the old one
Depends on: Task 1, Task 2, Task 3
Data: none
Execution: manual
Preconditions: two pre-releases built from the same signing secrets, the older one installed on the phone.
Steps:
1. Open the app once, so it holds its settings.
2. Download the newer APK and open it.
3. Tap Install without uninstalling the app first.
Expected: Android offers "Update", not a conflict or "App not installed", and the app opens with its settings kept.

### ST-12: No secret value appears in the log or the notes
Covers: staging-app-distribution/Secrets stay out of sight/Build log and notes
Depends on: Task 1, Task 2
Data: none
Execution: manual
Preconditions: a finished build from ST-1.
Steps:
1. Open the whole log of the build run and search it for the backend address, the app token, the key password and the first 20 characters of the key.
2. Read the pre-release notes.
3. Search the repository's files for the same values.
Expected: none of the four values appears in the log, the notes or the repository.

### ST-13: Owner sets up the build from the guide alone
Covers: staging-app-distribution/Setup and install guide/Owner sets up the build
Depends on: Task 5
Data: none
Execution: manual
Preconditions: a repository (a fork or a scratch copy) with none of the build's secrets set. The person has not read the workflow.
Steps:
1. Open the guide from the README.
2. Follow it to create the test signing key and set every secret.
3. Follow it to run the build by hand and find the pre-release.
Expected: every secret the build needs is in the guide, with its name, what it holds and whether it is required. The build ends green and a pre-release appears, with no step that needs the workflow file.

### ST-14: Tester installs the app from the guide
Covers: staging-app-distribution/Setup and install guide/Tester installs the app
Depends on: Task 2, Task 5
Data: none
Execution: manual
Preconditions: an Android phone, and a tester with access to the repository who has not seen the guide.
Steps:
1. On the phone, open the guide and sign in to GitHub.
2. Download the APK from the newest pre-release.
3. Allow installs from the browser if Android asks, and install.
4. Open the app.
Expected: the APK downloads, installs and opens on the camera screen.

## Traceability

| Scenario | Cases |
|---|---|
| App change pushed to staging | ST-1 |
| Push that does not touch the app | ST-2 |
| Other branches and pull requests | ST-3 |
| Manual run | ST-4 |
| App not on the branch yet | Scope (workflow tests) |
| Pre-release created | ST-5 |
| Not marked as a production release | ST-5 |
| Failed build publishes nothing | Scope (workflow tests) |
| App reaches the staging backend | ST-8 |
| Changing the staging backend | ST-9 |
| Token switch on | ST-10 |
| Missing backend secret | ST-6 |
| Plain HTTP staging backend | ST-8 |
| Any other plain HTTP server | Scope (app unit tests) |
| Other builds unchanged | Scope (app unit tests) |
| New build installs over the old one | ST-11 |
| Missing signing secret | ST-7 |
| Build log and notes | ST-12 |
| Owner sets up the build | ST-13 |
| Tester installs the app | ST-14 |
