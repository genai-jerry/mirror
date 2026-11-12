# Design — installable staging Android app

Epic: genai-jerry/mirror#61. Repo: `genai-jerry/mirror` only. Reads with
`proposal.md`, `specs/staging-app-distribution/spec.md`, `tasks.md` and
`system-tests/`.

Grounded in the code on `staging` (the mirror v1 app and the backend
deployment epic): `app/app/build.gradle.kts`, `app/gradle.properties`,
`app/app/src/main/AndroidManifest.xml`,
`app/app/src/main/res/xml/network_security_config.xml`, `BackendConfig.kt`,
`.github/workflows/backend-deploy.yml`, `.github/workflow-tests/`,
`scripts/gate.sh` and `docs/deployment.md`.

## Decisions

### D1 — One new workflow, "Staging app", builds and publishes the app; nothing else in the repository runs it
The file is `.github/workflows/staging-app.yml`. It has two jobs: `build`
(the build workflow task) and `publish` (the pre-release task). It is a
separate file from "Backend deploy", which keeps its own triggers unchanged.

Why: the backend deploy and the app build start on different files and
publish to different places. One file each keeps both trigger lists short
and testable on their own.

### D2 — The build starts on a push to `staging` that changes `app/**` or the workflow file, or by hand; it never starts on `main`, another branch or a pull request
`on.push.branches: [staging]`, `on.push.paths: ["app/**",
".github/workflows/staging-app.yml"]`, and `workflow_dispatch` with no
inputs. The first step of `build` fails a manual run on any branch but
`staging` with `Staging app builds run only from staging`.

Why: this is the spec's trigger rule, and it copies the backend deploy's
pattern (branch filter, path filter, then a branch guard for the manual
start that GitHub's branch picker cannot restrict).

### D3 — The workflow reads its secrets from the existing `staging` GitHub Environment
The `build` job declares `environment: staging`. It reads five new secrets,
`APP_BACKEND_URL`, `APP_SIGNING_KEYSTORE`, `APP_SIGNING_STORE_PASSWORD`,
`APP_SIGNING_KEY_ALIAS` and `APP_SIGNING_KEY_PASSWORD`, and the existing
`APP_TOKEN`. `APP_TOKEN` is optional: unset means the app sends no token,
which matches a backend that has no `APP_TOKEN`.

Why: the staging backend already reads `APP_TOKEN` from this environment, so
reading the same secret means the app and the backend can never disagree on
the token. One place holds every staging setting.

### D4 — The staging backend address is a full URL secret, such as `http://203.0.113.10:8000/`
`APP_BACKEND_URL` holds the scheme, the host, the port and an optional path.
The workflow refuses a value that does not start with `http://` or
`https://`, or that holds a space, a quote, a backslash or a line break. The
refusal names the secret and never prints its value.

Why: the backend has no domain and listens on plain HTTP port 8000
(`docs/deployment.md`). A full URL lets a later HTTPS backend change only
the secret. The character check keeps the value safe inside the generated
Kotlin string and network rule.

### D5 — A third app flavour, `staging`, with its own app id `com.genaijerry.mirror.staging` and the name "Mirror staging" on the phone
The flavour sits beside `dev` and `systemTest` in the `environment`
dimension. It sets `applicationIdSuffix = ".staging"` and its own version
(D9). A flavour resource file renames the app on the home screen.

Why: a separate app id lets a tester keep a developer build and the staging
build on one phone. The visible name makes clear it is a test build
(the proposal's interpretation 9).

### D6 — The workflow passes every secret to Gradle as an environment variable, never on a command line
Each value reaches Gradle as an `ORG_GRADLE_PROJECT_<property>` variable set
in the step's `env:` block. Gradle turns these into the project properties
`mirrorStagingBackendUrl`, `mirrorStagingAppToken`,
`mirrorStagingKeystoreFile`, `mirrorStagingStorePassword`,
`mirrorStagingKeyAlias`, `mirrorStagingKeyPassword` and
`mirrorStagingVersionCode`. They hold no dot, unlike the existing
`mirror.systemTestBackendUrl` and `mirror.systemTestAppToken`.

Why: a `-P` argument is visible in the process list and can be echoed in a
Gradle error. An environment variable is neither, and GitHub masks it in the
log as well. The names hold no dot because `app/gradlew` runs under
`/bin/sh`, which is `dash` on the Ubuntu runners, and `dash` drops every
environment variable whose name is not a shell identifier before Gradle
starts. A dotted name would never reach the build (found in review of the
build workflow task).

### D7 — The build reads the backend address and token at build time, so a changed secret needs no code change
`app/app/build.gradle.kts` reads `mirrorStagingBackendUrl` and
`mirrorStagingAppToken` exactly as it reads the `systemTest` ones today, and
writes them into `BuildConfig.BACKEND_BASE_URL` and
`BuildConfig.BACKEND_APP_TOKEN`. `BackendConfig` is unchanged. Unset, the
staging address falls back to the developer address `http://10.0.2.2:8000/`
and the token to empty, so the gate's `assembleDebug` and `lint`, which build
every flavour, still pass with nothing set.

Why: `BackendConfig` already reads the address from `BuildConfig` only, which
is the profile's rule. The workflow, not the build file, makes sure the real
value is set (D4).

### D8 — One fixed test key signs every staging build; the key is a base64 keystore secret written to a private temporary file for the build only
`APP_SIGNING_KEYSTORE` holds a PKCS12 keystore encoded as base64. The workflow
decodes it with `umask 077` into `$RUNNER_TEMP/staging-signing.p12`, passes
the path as `mirrorStagingKeystoreFile`, and deletes it in an `always()`
step. The build file creates a `staging` signing config from the four signing
properties and gives it to the `stagingRelease` variant only. Without the
properties the staging release build stays unsigned. The workflow checks the
signed APK exists, so an unsigned build fails the run.

Why: Android installs an update only when it carries the same signature. A
key that lives only in secrets and on the runner's disk for one job never
reaches a file in the repository or the log.

### D9 — The version number is the workflow's run number times 100 plus the run attempt
`versionCode = github.run_number * 100 + github.run_attempt`, passed as
`mirrorStagingVersionCode`. The version name becomes
`0.1.0-staging.<versionCode>`. The build fails if the attempt is above 99.
The workflow file must never be renamed, because a rename restarts the run
number.

Why: the run number rises with every run of this workflow, so each build is
higher than the one before and installs as an update. Adding the attempt
gives a re-run its own number, so its pre-release tag never clashes with the
first try.

### D10 — The workflow runs the app's dev unit suite before the staging build; a failure stops the run
The `build` job runs `./gradlew testDevDebugUnitTest`, the gate's own suite,
then `./gradlew assembleStagingRelease`. It installs JDK 21 and the Android
SDK first.

Why: the spec says a failed suite publishes nothing. The dev suite is what
the gate runs. Some existing tests assert dev values, such as an empty token,
and would fail under the staging flavour for no real reason.

### D11 — The pre-release is a separate job that runs only after a green build, tagged `staging-app-<versionCode>`, and never marked latest
`publish` has `needs: build` and no `if:`. It downloads the APK the build
uploaded and runs
`gh release create staging-app-<versionCode> <apk> --prerelease --latest=false --target <commit>`.
The title is `Mirror staging <versionName>`. The notes name the commit, the
version and the run link, and nothing else.

Why: GitHub skips a job whose `needs` failed, so a failed build can never
publish. The `--latest=false` flag keeps the front page from showing a test
build as the latest release.

### D12 — Plain HTTP is allowed to the staging backend's host only, by a network rule the build writes for the staging flavour
A Gradle task fills a committed template,
`app/app/network-security/staging.xml`, with the host from
`mirrorStagingBackendUrl`. It writes the result as
`res/xml/network_security_config_staging.xml` in a generated resource folder
of the staging variants only. A staging manifest overlay points
`android:networkSecurityConfig` at that file. The staging rule lists only the
staging host, not the local addresses. The `dev` and `systemTest` flavours
keep the existing `network_security_config.xml`, unchanged.

Why: Android reads plain-HTTP permission from a resource file, which cannot
read a build property. Generating the file from the same property as the
address keeps the address in one secret. A separate file name means the dev
and test builds cannot be affected.

### D13 — No new stack, and no new tool: the stack is the one the mirror v1 epic chose
This epic adds a workflow, a flavour, a network rule and a guide. It uses
Gradle, the Android Gradle plugin and Python's `unittest` and PyYAML for the
workflow tests, all of which are on `staging` already. It chooses no new
library and no new test runner.

Why: the profile on this epic's branch still says "Not chosen yet" only
because the epic branch was cut from `main` before the mirror v1 app reached
`main`. The real profile arrives with the app.

### D14 — The workflow tests prove the triggers and shell steps without an Android SDK; a person proves the first real build
A new file, `.github/workflow-tests/test_staging_app.py`, follows
`test_backend_deploy.py`. It runs with `python3
.github/workflow-tests/test_staging_app.py`. It needs Python 3 and PyYAML and
no Android SDK.

Why: the factory's runners have no Android SDK, so no factory run can build
the APK. The guide's first-build section is what a person follows to prove
the rest.

## Task 1 — Workflow that builds and signs the staging app (#64)

Depends on: nothing. Builds `.github/workflows/staging-app.yml` with the
`build` job, and `.github/workflow-tests/test_staging_app.py`.

### Workflow shape

```yaml
name: Staging app
on:
  push:
    branches: [staging]
    paths:
      - "app/**"
      - ".github/workflows/staging-app.yml"
  workflow_dispatch:
permissions:
  contents: read
concurrency:
  group: staging-app
  cancel-in-progress: false
jobs:
  build:
    name: Build and sign the staging app
    runs-on: ubuntu-latest
    environment: staging
    permissions:
      contents: read
    outputs:
      version_code: ${{ steps.version.outputs.version_code }}
      version_name: ${{ steps.version.outputs.version_name }}
      apk_name:     ${{ steps.version.outputs.apk_name }}
```

### Build job steps, in this order

| # | Step name | What it does |
|---|---|---|
| 1 | `Only staging` | `BRANCH=${{ github.ref_name }}`; any value but `staging` prints `::error::Staging app builds run only from staging` and exits 1 |
| 2 | `Check out` | `actions/checkout@v4` |
| 3 | `App present` | Fails with `::error::app/ is not on ${BRANCH}; the mirror v1 app must reach staging first` when `app/gradlew` or `app/app/build.gradle.kts` is missing |
| 4 | `Required settings present` | See below |
| 5 | `Version` | Computes the version (D9) and writes `version_code`, `version_name`, `apk_name` to `$GITHUB_OUTPUT` |
| 6 | `Set up JDK` | `actions/setup-java@v4`, `distribution: temurin`, `java-version: "21"` (the profile's JDK 21 gotcha) |
| 7 | `Set up Android SDK` | `android-actions/setup-android@v3` with `packages: platform-tools`, which accepts the licences. The list is explicit because the action's default asks for the retired `tools` package (bug #93). The Android Gradle plugin then downloads platform 37.2 and build-tools 37.0.0 itself |
| 8 | `Set up Gradle` | `gradle/actions/setup-gradle@v4`, for the wrapper and the cache |
| 9 | `Unit tests` | `cd app && ./gradlew testDevDebugUnitTest` (D10) |
| 10 | `Signing key` | `umask 077`; `printf '%s' "$APP_SIGNING_KEYSTORE" \| base64 -d > "$RUNNER_TEMP/staging-signing.p12"`; fails with `::error::Secret APP_SIGNING_KEYSTORE is not valid base64` when decoding fails |
| 11 | `Build the staging app` | `cd app && ./gradlew assembleStagingRelease`, with every value in `env:` (D6) |
| 12 | `APK signed` | Fails with `::error::The staging APK was not signed` unless `app/app/build/outputs/apk/staging/release/app-staging-release.apk` exists; copies it to `$RUNNER_TEMP/$APK_NAME` |
| 13 | `Keep the APK` | `actions/upload-artifact@v4`, name `staging-apk`, `retention-days: 1`, `if-no-files-found: error` |
| 14 | `Clean up` | `if: always()`; `rm -f "$RUNNER_TEMP/staging-signing.p12"` |

Only `Clean up` carries an `if:`. No step has `continue-on-error`.

**`Required settings present`** reads the six secrets in its `env:` block.
It fails, naming every missing one as
`::error::Secret <NAME> is not set in the staging environment`, when any of
`APP_BACKEND_URL`, `APP_SIGNING_KEYSTORE`, `APP_SIGNING_STORE_PASSWORD`,
`APP_SIGNING_KEY_ALIAS` or `APP_SIGNING_KEY_PASSWORD` is empty. `APP_TOKEN`
may be empty. It then checks `APP_BACKEND_URL` (D4): it must match
`^https?://[^/[:space:]'"\\]+(/[^[:space:]'"\\]*)?$`, or the step prints
`::error::Secret APP_BACKEND_URL must be a URL starting with http:// or https://`.
`APP_TOKEN` must hold no quote, backslash or line break, or the step prints
`::error::Secret APP_TOKEN contains a quote, a backslash or a line break`.
No message prints a value.

**`Version`** reads `RUN_NUMBER=${{ github.run_number }}` and
`RUN_ATTEMPT=${{ github.run_attempt }}`:

```bash
if [ "$RUN_ATTEMPT" -gt 99 ]; then
  echo "::error::Run attempt ${RUN_ATTEMPT} is above 99; start a new run instead"; exit 1
fi
code=$(( RUN_NUMBER * 100 + RUN_ATTEMPT ))
echo "version_code=${code}"                     >> "$GITHUB_OUTPUT"
echo "version_name=0.1.0-staging.${code}"       >> "$GITHUB_OUTPUT"
echo "apk_name=mirror-staging-${code}.apk"      >> "$GITHUB_OUTPUT"
```

The `0.1.0` is the app's `defaultConfig.versionName`. The staging flavour
task makes the build file produce the same version name from the same code,
so the APK's own version and the pre-release name agree.

**`Build the staging app`** `env:` block:

```yaml
ORG_GRADLE_PROJECT_mirrorStagingBackendUrl:   ${{ secrets.APP_BACKEND_URL }}
ORG_GRADLE_PROJECT_mirrorStagingAppToken:     ${{ secrets.APP_TOKEN }}
ORG_GRADLE_PROJECT_mirrorStagingKeystoreFile: ${{ runner.temp }}/staging-signing.p12
ORG_GRADLE_PROJECT_mirrorStagingStorePassword: ${{ secrets.APP_SIGNING_STORE_PASSWORD }}
ORG_GRADLE_PROJECT_mirrorStagingKeyAlias:     ${{ secrets.APP_SIGNING_KEY_ALIAS }}
ORG_GRADLE_PROJECT_mirrorStagingKeyPassword:  ${{ secrets.APP_SIGNING_KEY_PASSWORD }}
ORG_GRADLE_PROJECT_mirrorStagingVersionCode:  ${{ steps.version.outputs.version_code }}
```

No Gradle call uses `--info`, `--debug`, `--scan` or `--stacktrace`, and no
step uses `set -x`. These options can print property values.

### Workflow tests (`.github/workflow-tests/test_staging_app.py`)

Copy the helpers from `test_backend_deploy.py` (`load_workflow`,
`glob_to_regex`, `push_triggers`, `run_step`), with `step()` taking a job
name. Extend nothing in the backend test file. The test classes:

- **Triggers:** only `push` and `workflow_dispatch`; no `pull_request` or
  `pull_request_target`. `push.branches` is `[staging]`. A change under
  `app/` or to the workflow file triggers on `staging`. The same change on
  `main`, `factory/epic-61` or `feature/x` does not. A push of only
  `README.md`, `docs/…`, `openspec/…`, `backend/…`, `deploy/…`,
  `.github/workflows/backend-deploy.yml` or `.github/workflow-tests/…` does
  not trigger.
- **Manual run:** `workflow_dispatch` has no inputs. `Only staging` is the
  first step, reads `github.ref_name`, passes `staging`, and fails `main`,
  `Staging`, `factory/epic-61` and the empty string with its message.
- **App present:** fails in an empty folder with the exact message; passes
  with `app/gradlew` and `app/app/build.gradle.kts` present.
- **Required settings:** with every secret set it passes. Unset each
  required secret in turn: it fails and names that secret. Unset two: it
  names both. With `APP_TOKEN` empty it passes. A URL of `ftp://x`, `x`,
  one with a space or a quote fails with the URL message. In every case,
  stdout and stderr contain none of the secret values the test set.
- **Version:** run number 7 and attempt 1 give `701`,
  `0.1.0-staging.701`, `mirror-staging-701.apk`. Attempt 2 gives `702`.
  Attempt 100 fails.
- **Signing key:** a base64 of known bytes decodes to those bytes with mode
  `600`. A value that is not base64 fails with the message.
- **APK signed:** fails without the signed APK file; passes and copies it
  when the file exists.
- **Step order:** the table above, exactly.
- **Secrets stay out of the log:** every secret reaches a step through
  `env:` only, never inside a `run:` script. The `Build the staging app` step
  passes values only as `ORG_GRADLE_PROJECT_` variables, and its `run:`
  holds no `-P`, `--info`, `--debug`, `--scan` or `--stacktrace`. No `run:`
  contains `set -x`.
- **Failures stop the run:** no step except `Clean up` has `if:`; no step or
  job has `continue-on-error`. `Clean up` has `if: always()`. Every `run:`
  parses with `bash -n`.

Steps run with `bash -e -c`, as GitHub runs them. A test that needs
`GITHUB_OUTPUT` or `RUNNER_TEMP` points them at a temporary folder.

### Failure modes

| Spec scenario | What happens |
|---|---|
| App change pushed to staging | The path filter matches; the build runs |
| Push that does not touch the app | The path filter does not match; no run |
| Other branches and pull requests | The branch filter and the missing `pull_request` trigger mean no run |
| Manual run | `Only staging` passes on `staging` and fails elsewhere before anything else runs |
| App not on the branch yet | `App present` fails with its message; `publish` is skipped |
| Missing backend secret, Missing signing secret | `Required settings present` fails before the JDK is installed; `publish` is skipped |
| Failed build publishes nothing | `Unit tests` or `Build the staging app` fails; `publish` is skipped |
| Changing the staging backend | The build reads the secret at build time (D7) |
| Token switch on | `APP_TOKEN` reaches the build (D3, D6) |
| New build installs over the old one | The version rises with every run (D9) |
| Build log and notes | Secrets pass through `env:` only (D6) |

## Task 2 — Pre-release that publishes the APK (#65)

Depends on: the build workflow task. Adds the `publish` job to
`.github/workflows/staging-app.yml` and its tests to
`.github/workflow-tests/test_staging_app.py`.

```yaml
  publish:
    name: Publish the staging pre-release
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
```

No `environment:` and no secret except `GITHUB_TOKEN`: the job never sees
the backend address, the token or the key.

Steps, in this order:

| # | Step name | What it does |
|---|---|---|
| 1 | `Fetch the APK` | `actions/download-artifact@v4`, name `staging-apk`, into `$RUNNER_TEMP/apk` |
| 2 | `Create the pre-release` | See below |
| 3 | `Summary` | Writes `Published Mirror staging <version name> for <short commit>` to `$GITHUB_STEP_SUMMARY` |

**`Create the pre-release`** `env:` holds `GH_TOKEN: ${{ github.token }}`,
`SHA: ${{ github.sha }}`, `REPO: ${{ github.repository }}`,
`RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}`,
and the build job's three outputs. It runs:

```bash
tag="staging-app-${VERSION_CODE}"
notes="$(printf 'Staging build of the Mirror app, for testers.\n\nVersion: %s (%s)\nCommit: %s\nBuilt by: %s\n\nInstall it on an Android phone as docs/staging-app.md describes.\n' \
  "$VERSION_NAME" "$VERSION_CODE" "$SHA" "$RUN_URL")"
gh release create "$tag" "$RUNNER_TEMP/apk/$APK_NAME" \
  --repo "$REPO" --target "$SHA" \
  --title "Mirror staging ${VERSION_NAME}" \
  --notes "$notes" --prerelease --latest=false
```

`gh` is on `ubuntu-latest`. The tag is created on the built commit.

**Tests:** `publish` needs `build` and has no `if:`. Its permissions are
`contents: write` only, and the workflow-level permissions stay
`contents: read`. It has no `environment:`, and its YAML names no secret but
the run's own token. The create step contains `--prerelease` and
`--latest=false` and never `--latest` alone or `--draft`. Its tag starts
`staging-app-`. Run with a fake `gh` on `PATH` that records its arguments:
the tag, the title, the target commit and the APK path are right, and the
notes contain the commit, the version name and code, and the run link.
Every `run:` parses with `bash -n`.

### Failure modes

| Spec scenario | What happens |
|---|---|
| Pre-release created | One APK attached; notes name the commit and the version |
| Not marked as a production release | `--prerelease --latest=false` |
| Failed build publishes nothing | `needs: build` with no `if:`, so GitHub skips the job |
| Manual run | Publishes from the manual run's commit, like a push |
| Build log and notes | The job never receives a backend, token or key secret, so it cannot print one |
| A tag already exists | `gh release create` fails and the run goes red. D9 makes this happen only if the workflow file was renamed |

## Task 3 — Staging flavour of the app, signed, with a rising version (#66)

Depends on: the build workflow task, and the app being on this epic's
branch (see `tasks.md`). Touches `app/app/build.gradle.kts`,
`app/gradle.properties`, a new
`app/app/src/staging/res/values/strings.xml`, the README's flavour table, and
`.factory/profile.json`.

In `app/app/build.gradle.kts`, beside the existing `systemTest` reads:

```kotlin
val stagingBackendUrl: String =
    (project.findProperty("mirrorStagingBackendUrl") as String?)?.trim()
        ?.takeIf { it.isNotEmpty() } ?: "http://10.0.2.2:8000/"
val stagingAppToken: String = appToken("mirrorStagingAppToken")
val stagingVersionCode: Int =
    (project.findProperty("mirrorStagingVersionCode") as String?)?.toIntOrNull() ?: 1
```

The URL is checked with `java.net.URI`: the scheme must be `http` or
`https` and the host must not be empty. Otherwise configuration fails with
`mirrorStagingBackendUrl is not an http or https URL`, without the value.

The flavour:

```kotlin
create("staging") {
    dimension = "environment"
    applicationIdSuffix = ".staging"
    versionCode = stagingVersionCode
    versionName = "0.1.0-staging.$stagingVersionCode"
    buildConfigField("String", "BACKEND_BASE_URL", "\"$stagingBackendUrl\"")
    buildConfigField("String", "BACKEND_APP_TOKEN", "\"$stagingAppToken\"")
}
```

The flavour sets `versionName` in full, rather than a suffix, so it matches
the workflow's version name exactly.

The signing config is created only when all four signing properties are
set and the keystore file exists:

```kotlin
val stagingSigning = listOf(
    "mirrorStagingKeystoreFile", "mirrorStagingStorePassword",
    "mirrorStagingKeyAlias", "mirrorStagingKeyPassword",
).map { (project.findProperty(it) as String?).orEmpty() }

signingConfigs {
    if (stagingSigning.all { it.isNotEmpty() } && file(stagingSigning[0]).isFile) {
        create("staging") {
            storeFile = file(stagingSigning[0])
            storePassword = stagingSigning[1]
            keyAlias = stagingSigning[2]
            keyPassword = stagingSigning[3]
            storeType = "pkcs12"
        }
    }
}
```

Apply it to the `staging` + `release` variant only. Use
`productFlavors.getByName("staging").signingConfig =
signingConfigs.findByName("staging")`. The `debug` build type sets its own
debug key, which wins over the flavour's, so only `stagingRelease` uses the
test key. The `dev` and
`systemTest` flavours are untouched.

`app/app/src/staging/res/values/strings.xml` holds one string,
`app_name` = `Mirror staging`. Every other string stays in main.

`app/gradle.properties` gains the empty defaults `mirrorStagingBackendUrl=`
and `mirrorStagingAppToken=`, with a comment saying the workflow sets them
and they are never committed with values.

**Profile and README.** The README's flavour table gains the `staging` row.
The profile gotcha about "two flavours (dev and systemTest)" says three. The
backend URL convention names the staging property too. The gate's commands
stay as they are.

**Tests** (in the dev unit suite, `app/app/src/test/…`): the existing
`BackendConfigTest` stays green for `dev`. Add no test that needs the
staging flavour to run. The build file's checks are proven by the commands
below, run by the implementer where an SDK exists, and otherwise by the
person's first build:

- `./gradlew testDevDebugUnitTest assembleDebug lint` with nothing set:
  green.
- `./gradlew assembleStagingRelease -PmirrorStagingBackendUrl=ftp://x`:
  fails with the URL message.

### Failure modes

| Spec scenario | What happens |
|---|---|
| App reaches the staging backend | `BuildConfig.BACKEND_BASE_URL` is the secret's address |
| Changing the staging backend | A new run reads the changed secret; no file changes |
| Token switch on | `BuildConfig.BACKEND_APP_TOKEN` is `APP_TOKEN`, which `BackendConfig` already sends |
| New build installs over the old one | Same key every build, and a higher `versionCode` |
| Other builds unchanged | `dev` and `systemTest` keep their app id, address, token and version |
| Signing properties missing | The staging release builds unsigned; the workflow's `APK signed` step fails the run |

## Task 4 — Plain HTTP to the staging backend address only (#67)

Depends on: the staging flavour task. Touches `app/app/build.gradle.kts`,
and adds `app/app/network-security/staging.xml`,
`app/app/src/staging/AndroidManifest.xml` and a unit test.

**The template** `app/app/network-security/staging.xml`, outside `res/` so
it is never packaged as is:

```xml
<network-security-config>
    <base-config cleartextTrafficPermitted="false" />
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="false">@STAGING_HOST@</domain>
    </domain-config>
</network-security-config>
```

**The generator.** A Gradle `Copy` task, `generateStagingNetworkConfig`,
reads the template, replaces `@STAGING_HOST@` with
`URI(stagingBackendUrl).host`, and writes
`xml/network_security_config_staging.xml` into
`build/generated/staging-network/res`. The task's input is the host, so a
changed secret reruns it. Register it with
`androidComponents.onVariants(selector().withFlavor("environment" to "staging"))`
and `variant.sources.res?.addGeneratedSourceDirectory(...)`.

**The manifest overlay** `app/app/src/staging/AndroidManifest.xml` sets
`android:networkSecurityConfig="@xml/network_security_config_staging"` on
`<application>` with `tools:replace="android:networkSecurityConfig"`.

`app/app/src/main/res/xml/network_security_config.xml` does not change. It
keeps `127.0.0.1`, `localhost` and `10.0.2.2` for `dev` and `systemTest`.

**Unit test** `NetworkSecurityConfigTest.kt`, in the dev unit suite, plain
JUnit with the JDK's XML parser. Gradle runs unit tests in the module's
folder, `app/app`, so the test reads both files by relative path:

- the staging template refuses plain HTTP in its base config;
- it has exactly one plain-HTTP domain rule, holding exactly one domain,
  `@STAGING_HOST@`, with `includeSubdomains="false"`;
- the main config refuses plain HTTP in its base config and allows it to
  exactly `127.0.0.1`, `localhost` and `10.0.2.2`.

Name the template's placeholder in one place in the test, and the same
string in the build file.

### Failure modes

| Spec scenario | What happens |
|---|---|
| Plain HTTP staging backend | The staging rule allows the secret's host |
| Any other plain HTTP server | The staging base config refuses plain HTTP, and the rule lists one host |
| Other builds unchanged | `dev` and `systemTest` use the main file, which the test pins |
| The address is an IP | Android accepts an IP address in `<domain>`, as the main file already does for `127.0.0.1` |
| The address changes | The generator's input changes, so the next build writes the new host |

## Task 5 — Setup and install guide for the staging app (#68)

Depends on: the pre-release task, the staging flavour task and the
plain-HTTP task. Adds `docs/staging-app.md`, a README link, and
`.github/workflow-tests/test_staging_app_guide.py`.

The guide follows `docs/deployment.md` in tone and layout:

1. **What builds when.** A push to `staging` that changes `app/` or the
   workflow file. A manual run on `staging`. Nothing else. Each build is a
   pre-release named `Mirror staging <version>`.
2. **Secrets.** A table: name, required or optional, what it holds. All six
   live in **Settings → Environments → `staging`**. `APP_TOKEN` is the one
   the backend already uses.
3. **Making the test key.** One `keytool -genkeypair -storetype PKCS12
   -keyalg RSA -keysize 4096 -validity 10000 -alias mirror-staging …`
   command, then `base64 -w0` to make `APP_SIGNING_KEYSTORE`. Keep the file
   in a password manager. Losing the key means every tester must uninstall
   once.
4. **The first build.** Actions → **Staging app** → **Run workflow** on
   `staging`, then where the pre-release appears. A table of every
   `::error::` message the workflow prints and what to do.
5. **Installing on a phone.** Sign in to GitHub in the phone's browser,
   open Releases, download the APK from the newest pre-release, allow
   installs from the browser, install, open. Installing a newer build is
   the same steps, and Android offers "Update".
6. **What the factory cannot check.** A person runs the first build and
   installs it.

**Test:** like `deploy/tests/test_setup_guide.py`, the guide's secret table
must hold exactly the `secrets.` names the workflow reads, except
`GITHUB_TOKEN`. The README must link `docs/staging-app.md`. Run with
`python3 .github/workflow-tests/test_staging_app_guide.py`.

## Data

No database change and no migration. No system test data sets
(`system-tests/test-data.md`), so there is no loader task.

## Rollout and rollback

- **Order.** The two workflow tasks can merge onto the epic branch first.
  Until the app is on the branch the workflow's `App present` step fails a
  manual run, and the path filter means no push starts it. The flavour, the
  plain-HTTP rule and the guide follow when the app arrives.
- **Before the first build.** An owner sets the six secrets in the `staging`
  environment, following the guide.
- **First build.** A person runs it by hand after gate GS and installs it
  (ST-1 to ST-14).
- **Rollback.** Revert the epic's integration merge on `staging`. The
  workflow then no longer exists there, and published pre-releases stay
  until a person deletes them. Removing the secrets does no harm to the
  backend, except `APP_TOKEN`, which the backend also reads and must stay.

## Open questions

None that block a task. Two facts only a real run can confirm, both covered
by the guide's first build:

- the Android Gradle plugin downloads platform 37.2 and build-tools 37.0.0
  on the runner once `setup-android` has accepted the licences;
- `gh release create --latest=false` behaves as documented on the runner's
  `gh`.
