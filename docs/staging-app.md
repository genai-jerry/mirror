# The staging app: setup and install

This guide sets up the staging build of the Android app and shows a tester how
to install it. It covers every secret the build reads, how to make the test
signing key, how to run the first build by hand, and how to install the app on
a phone. You do not need to read the workflow or the app's build file.

The workflow is `.github/workflows/staging-app.yml` ("Staging app" in the
Actions tab). Each build talks to the staging backend that
[Deploying the backend](deployment.md) sets up.

## 1. What builds when

**What starts a build.** A push to `staging` that changes at least one of
these:

- anything under `app/`
- `.github/workflows/staging-app.yml`

A push that changes only documents (`docs/`, `openspec/`), the backend, the
deployment files or the factory's own files builds nothing. No other branch
builds, and a pull request never builds.

**Starting one by hand.** Open Actions → **Staging app** → **Run workflow**,
choose `staging` in the branch list, and press **Run workflow**. Any other
branch fails at once with `Staging app builds run only from staging`.

**What one run does.**

1. Checks that every required secret is set. If one is missing, the run fails
   and names it, before anything is built.
2. Runs the app's unit tests. If a test fails, the run stops here.
3. Builds the staging app, signed with the test key, with the staging
   backend's address and the app token from the secrets.
4. Publishes a GitHub **pre-release** named `Mirror staging <version>`, with
   the app file (`mirror-staging-<number>.apk`) attached. The pre-release is
   never marked as the repository's latest release.

If any step fails, no pre-release is published. Every build gets a higher
version number than the one before, so a new build installs over the old one.

On the phone the app is called **Mirror staging**. It is a separate app from a
developer's build, so both can be installed on one phone.

## 2. Secrets

Set these in **Settings → Environments → `staging`**, under **Environment
secrets**. This is the same `staging` environment the backend deploy uses; if
it does not exist yet, create it as section 5 of
[Deploying the backend](deployment.md#5-creating-the-environments) says. There
are no repository-wide secrets to set.

| Name | Required | What it holds |
|---|---|---|
| `APP_BACKEND_URL` | required | The staging backend's address, as a full URL with the port, such as `http://staging.example.com:8000/`. It must start with `http://` or `https://`, and hold no space, quote, backslash or line break. The app may use plain HTTP to this address only. |
| `APP_TOKEN` | optional, default unset | The token the app sends to the backend on every request. It is the **same secret** the backend deploy already reads, so the app and the backend always agree. Unset means the app sends no token. It must hold no quote, backslash or line break. |
| `APP_SIGNING_KEYSTORE` | required | The test signing key: the keystore file from section 3, encoded as base64 (one long line of text). |
| `APP_SIGNING_STORE_PASSWORD` | required | The password of that keystore file. |
| `APP_SIGNING_KEY_ALIAS` | required | The name of the key inside the keystore. With the command in section 3 it is `mirror-staging`. |
| `APP_SIGNING_KEY_PASSWORD` | required | The password of the key. With the command in section 3 it is the same as `APP_SIGNING_STORE_PASSWORD`. |

Notes:

- To move the app to a different staging backend, change `APP_BACKEND_URL` and
  run the build again. No code changes.
- The publish step uses the run's own short-lived token. You do not create a
  `GITHUB_TOKEN` secret.
- Never put a real value from this table in a file in the repository, an issue
  or a pull request.

## 3. Making the test signing key

Do this once, on your own computer. You need `keytool`, which comes with any
Java (JDK) install, and `base64`.

1. **Create the keystore.** Choose a long password. `keytool` asks for it and
   for a name and organisation; any values will do.

   ```sh
   keytool -genkeypair -storetype PKCS12 -keyalg RSA -keysize 4096 \
     -validity 10000 -alias mirror-staging -keystore mirror-staging.p12
   ```

   This writes one file, `mirror-staging.p12`. A PKCS12 keystore uses one
   password for the file and the key, so the same password goes into both
   password secrets.

2. **Turn it into text for the secret.** On Linux:

   ```sh
   base64 -w0 mirror-staging.p12 > mirror-staging.p12.b64
   ```

   On a Mac:

   ```sh
   base64 -i mirror-staging.p12 -o mirror-staging.p12.b64
   ```

3. **Set the four signing secrets** in the `staging` environment (section 2):

   - the whole content of `mirror-staging.p12.b64` → `APP_SIGNING_KEYSTORE`;
   - the password → `APP_SIGNING_STORE_PASSWORD` and `APP_SIGNING_KEY_PASSWORD`;
   - `mirror-staging` → `APP_SIGNING_KEY_ALIAS`.

   With the GitHub command line tool you can set the keystore from the file
   instead of pasting it:

   ```sh
   gh secret set APP_SIGNING_KEYSTORE --env staging < mirror-staging.p12.b64
   ```

4. **Keep the key safe.** Store `mirror-staging.p12` and its password in a
   password manager, then delete both files from your computer. Never commit
   them.

**Keep using the same key.** Android installs an update only when it is signed
with the same key as the app already on the phone. If the key is lost or
replaced, every tester must uninstall Mirror staging once before the next build
installs.

## 4. The first build

The factory cannot build the Android app, so a person runs the first build and
checks it.

1. Make sure the app (`app/`) is on `staging`. If it is not, the run fails with
   `app/ is not on staging; the mirror v1 app must reach staging first`.
2. Set the secrets (sections 2 and 3).
3. Open Actions → **Staging app** → **Run workflow**, choose `staging`, and
   press **Run workflow**. If the `staging` environment has required
   reviewers, approve the run when GitHub asks.
4. Wait for both jobs to go green: **Build and sign the staging app**, then
   **Publish the staging pre-release**. The first build takes longer, because
   the runner downloads the Android tools. The run's summary says
   `Published Mirror staging <version> for <commit>`.
5. Open the repository's **Releases** page (the **Releases** link on the right
   of the repository's front page). The new pre-release is at the top, named
   `Mirror staging 0.1.0-staging.<number>` and marked **Pre-release**. Its
   **Assets** list holds `mirror-staging-<number>.apk`, and its notes name the
   version, the commit and the run.

After this, every app change merged to `staging` builds and publishes on its
own.

**If the run fails:**

| The run says | What to do |
|---|---|
| `Staging app builds run only from staging` | You chose another branch. Run it again and choose `staging`. |
| `app/ is not on staging; the mirror v1 app must reach staging first` | The app has not been merged to `staging` yet. Wait for it, then run again. |
| `Secret <NAME> is not set in the staging environment` | Add that secret to the `staging` environment (section 2) and run again. The run lists every missing one. |
| `Secret APP_BACKEND_URL must be a URL starting with http:// or https://` | Fix `APP_BACKEND_URL`: a full URL such as `http://staging.example.com:8000/`, with no space, quote or line break. |
| `Secret APP_TOKEN contains a quote, a backslash or a line break` | Choose a token without those characters. Change it in the backend's settings too, because both read the same secret. |
| `Run attempt <n> is above 99; start a new run instead` | Do not press **Re-run** again. Start a new run with **Run workflow**. |
| `Secret APP_SIGNING_KEYSTORE is not valid base64` | Make the base64 text again (section 3, step 2) and paste the whole of it, on one line. |
| `The staging APK was not signed` | A signing secret is wrong, or the passwords do not match the keystore. Check the four signing secrets against section 3. |
| The **Unit tests** step fails | An app test failed on `staging`. That is a code problem, not a setup problem: tell the developers. Nothing was published. |
| The **Build the staging app** step fails with `Keystore was tampered with, or password was incorrect` | `APP_SIGNING_STORE_PASSWORD` or `APP_SIGNING_KEY_PASSWORD` is wrong. |
| `The APK mirror-staging-<number>.apk is missing from the build files; nothing was published` | The build job did not hand over the APK. Run the workflow again; if it fails the same way, tell the developers. No pre-release or tag was created. |
| `The build job passed no version code; nothing was published` | The build job's version step did not reach the publish job. Tell the developers. No pre-release or tag was created. |
| **Create the pre-release** fails because the release already exists | The workflow file was renamed, which restarts the version numbers. Rename it back to `staging-app.yml`. |

## 5. Installing the app on a phone

You need an Android phone (Android 8.0 or later) and a GitHub account with
access to this repository.

1. **Sign in to GitHub on the phone.** Open the phone's browser (Chrome, for
   example), go to `github.com` and sign in. Use the browser, not the GitHub
   app: the GitHub app cannot install an app file.
2. **Open the newest pre-release.** Open this repository, then **Releases**.
   The newest build is at the top, named `Mirror staging 0.1.0-staging.<number>`.
3. **Download the app file.** Under **Assets**, tap
   `mirror-staging-<number>.apk`. If the browser warns that the file may be
   harmful, choose **Download anyway**.
4. **Open the download.** Tap the downloaded file in the browser's downloads
   or the notification.
5. **Allow installs from the browser, the first time only.** Android says the
   browser is not allowed to install unknown apps. Tap **Settings**, turn on
   **Allow from this source**, and go back.
6. **Install.** Tap **Install**. If Google Play Protect warns about an unknown
   developer, tap **More details** → **Install anyway**. This build is signed
   with the project's test key, not a Play Store key, so the warning is
   expected.
7. **Open the app.** It is called **Mirror staging** on the home screen. Allow
   the camera when it asks.

**Installing a newer build.** Do the same steps with the newest pre-release.
Do not uninstall the old build first. Android asks **Do you want to update this
app?** Tap **Update**. The app keeps its settings.

**If the install fails:**

| The phone says | What to do |
|---|---|
| **App not installed** or **The package conflicts with an existing package** | The installed build was signed with a different key (the key was replaced). Uninstall Mirror staging once, then install again. |
| **App not installed** when the phone already has a newer build | You downloaded an older build. Download the newest pre-release instead. |
| A 404 page instead of the release | You are not signed in, or your account has no access to the repository. Sign in, or ask the owner for access. |
| The app opens, but the language list says **Mirror could not load the languages** | The app cannot reach the staging backend: it is down, or `APP_BACKEND_URL` points somewhere else. Tell the owner. |

## 6. What the factory cannot check

The factory's runners have no Android tools, so no factory run builds the
app or installs it. A person runs the first build (section 4) and installs it
on a real phone (section 5). After that, each build publishes on its own, and
a tester confirms it by installing it.
