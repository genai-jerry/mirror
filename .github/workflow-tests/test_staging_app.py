"""Tests for .github/workflows/staging-app.yml, the build job (epic #61, task #64).

The factory's runners have no Android SDK, so these tests prove what can be
proved without one (design.md D14):

* the trigger filters, evaluated the way GitHub evaluates them, for each
  push the spec names;
* the build job's own shell steps, run with bash under the inputs that
  matter (branch, missing app, missing or malformed secrets, run number);
* the step order and the rules that keep secrets out of the log and stop
  the run on any failure.

A person proves the real build by hand (the guide's first-build section).

Run: python3 .github/workflow-tests/test_staging_app.py
Needs Python 3 and PyYAML.
"""

import base64
import os
import re
import stat
import subprocess
import tempfile
import unittest

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "staging-app.yml")

REQUIRED_SECRETS = (
    "APP_BACKEND_URL",
    "APP_SIGNING_KEYSTORE",
    "APP_SIGNING_STORE_PASSWORD",
    "APP_SIGNING_KEY_ALIAS",
    "APP_SIGNING_KEY_PASSWORD",
)

# Synthetic values only; none of them is a real address, token or key.
GOOD_SECRETS = {
    "APP_BACKEND_URL": "http://203.0.113.10:8000/",
    "APP_TOKEN": "tok-synthetic-4f1c9e",
    "APP_SIGNING_KEYSTORE": base64.b64encode(b"synthetic-keystore-bytes").decode(),
    "APP_SIGNING_STORE_PASSWORD": "store-pw-synthetic-81d2",
    "APP_SIGNING_KEY_ALIAS": "alias-synthetic-mirror",
    "APP_SIGNING_KEY_PASSWORD": "key-pw-synthetic-07ab",
}

STEP_ORDER = [
    "Only staging",
    "Check out",
    "App present",
    "Required settings present",
    "Version",
    "Set up JDK",
    "Set up Android SDK",
    "Set up Gradle",
    "Unit tests",
    "Signing key",
    "Build the staging app",
    "APK signed",
    "Keep the APK",
    "Clean up",
]


def load_workflow():
    with open(WORKFLOW) as fh:
        wf = yaml.safe_load(fh)
    # YAML 1.1 reads the bare key `on` as the boolean True.
    if True in wf and "on" not in wf:
        wf["on"] = wf.pop(True)
    return wf


def glob_to_regex(pattern):
    """GitHub filter glob: `**` crosses `/`, `*` does not."""
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile("^" + out + "$")


def matches_any(value, patterns):
    return any(glob_to_regex(p).match(value) for p in patterns)


def push_triggers(wf, branch, changed_files):
    push = wf["on"].get("push")
    if push is None:
        return False
    if "branches" in push and not matches_any(branch, push["branches"]):
        return False
    if "paths" in push:
        return any(matches_any(f, push["paths"]) for f in changed_files)
    return True


def step(wf, name, job="build"):
    for s in wf["jobs"][job]["steps"]:
        if s.get("name") == name:
            return s
    raise AssertionError("no step named %r in job %r" % (name, job))


def run_step(script, env, cwd):
    full_env = dict(os.environ)
    for key in list(full_env):
        if key in GOOD_SECRETS:
            del full_env[key]
    full_env.update(env)
    return subprocess.run(
        ["bash", "-e", "-c", script],
        env=full_env,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


class Triggers(unittest.TestCase):
    """Scenarios: App change pushed to staging; Push that does not touch the
    app; Other branches and pull requests."""

    def setUp(self):
        self.wf = load_workflow()

    def test_only_push_and_manual_start(self):
        self.assertEqual(set(self.wf["on"]), {"push", "workflow_dispatch"})

    def test_no_pull_request_trigger(self):
        for event in ("pull_request", "pull_request_target"):
            self.assertNotIn(event, self.wf["on"])

    def test_push_branches_is_staging_only(self):
        self.assertEqual(self.wf["on"]["push"]["branches"], ["staging"])

    def test_app_or_workflow_change_runs_on_staging(self):
        for files in (
            ["app/app/src/main/java/com/genaijerry/mirror/MainActivity.kt"],
            ["app/app/build.gradle.kts"],
            ["app/gradle.properties"],
            [".github/workflows/staging-app.yml"],
            ["README.md", "app/settings.gradle.kts"],
        ):
            self.assertTrue(push_triggers(self.wf, "staging", files), files)

    def test_app_change_on_other_branch_does_not_run(self):
        for branch in ("main", "factory/epic-61", "feature/x", "Staging", "staging-old"):
            for files in (["app/app/build.gradle.kts"], [".github/workflows/staging-app.yml"]):
                self.assertFalse(push_triggers(self.wf, branch, files), (branch, files))

    def test_push_that_does_not_touch_the_app_does_not_run(self):
        for files in (
            ["README.md"],
            ["docs/staging-app.md"],
            ["openspec/changes/61-staging-android-app/design.md"],
            ["backend/app/main.py"],
            ["deploy/compose.yaml"],
            [".github/workflows/backend-deploy.yml"],
            [".github/workflow-tests/test_staging_app.py"],
            [".factory/profile.json", ".claude/settings.json"],
        ):
            self.assertFalse(push_triggers(self.wf, "staging", files), files)


class ManualRun(unittest.TestCase):
    """Scenario: Manual run (the trigger and the branch check)."""

    def setUp(self):
        self.wf = load_workflow()
        self.guard = step(self.wf, "Only staging")

    def test_manual_start_has_no_inputs(self):
        self.assertIn("workflow_dispatch", self.wf["on"])
        self.assertFalse((self.wf["on"]["workflow_dispatch"] or {}).get("inputs"))

    def test_guard_is_the_first_step(self):
        self.assertEqual(self.wf["jobs"]["build"]["steps"][0]["name"], "Only staging")

    def test_guard_reads_the_branch_from_ref_name(self):
        self.assertEqual(self.guard["env"]["BRANCH"], "${{ github.ref_name }}")

    def test_guard_passes_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run_step(self.guard["run"], {"BRANCH": "staging"}, tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_guard_fails_any_other_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            for branch in ("main", "Staging", "factory/epic-61", ""):
                r = run_step(self.guard["run"], {"BRANCH": branch}, tmp)
                self.assertNotEqual(r.returncode, 0, branch)
                self.assertIn("::error::Staging app builds run only from staging", r.stdout)


class AppPresent(unittest.TestCase):
    """Scenario: App not on the branch yet."""

    MESSAGE = "::error::app/ is not on staging; the mirror v1 app must reach staging first"

    def setUp(self):
        self.s = step(load_workflow(), "App present")

    def test_fails_in_an_empty_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run_step(self.s["run"], {"BRANCH": "staging"}, tmp)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn(self.MESSAGE, r.stdout)

    def test_fails_with_only_one_of_the_two_files(self):
        for present in ("app/gradlew", "app/app/build.gradle.kts"):
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, present)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").close()
                r = run_step(self.s["run"], {"BRANCH": "staging"}, tmp)
                self.assertNotEqual(r.returncode, 0, present)
                self.assertIn(self.MESSAGE, r.stdout)

    def test_passes_with_the_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            for present in ("app/gradlew", "app/app/build.gradle.kts"):
                path = os.path.join(tmp, present)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").close()
            r = run_step(self.s["run"], {"BRANCH": "staging"}, tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class RequiredSettings(unittest.TestCase):
    """Scenarios: Missing backend secret; Missing signing secret; Token switch
    on; Build log and notes (the log)."""

    URL_MESSAGE = "::error::Secret APP_BACKEND_URL must be a URL starting with http:// or https://"
    TOKEN_MESSAGE = "::error::Secret APP_TOKEN contains a quote, a backslash or a line break"

    def setUp(self):
        self.s = step(load_workflow(), "Required settings present")

    def run_with(self, secrets):
        with tempfile.TemporaryDirectory() as tmp:
            return run_step(self.s["run"], secrets, tmp)

    def assert_no_secret_printed(self, r, secrets):
        out = r.stdout + r.stderr
        for name, value in secrets.items():
            if value:
                self.assertNotIn(value, out, name)

    def test_reads_every_secret_through_env(self):
        for name in GOOD_SECRETS:
            self.assertEqual(self.s["env"][name], "${{ secrets.%s }}" % name)

    def test_passes_with_every_secret_set(self):
        r = self.run_with(GOOD_SECRETS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_no_secret_printed(r, GOOD_SECRETS)

    def test_https_url_with_path_passes(self):
        secrets = dict(GOOD_SECRETS, APP_BACKEND_URL="https://staging.example.test/api/")
        r = self.run_with(secrets)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_missing_required_secret_is_named(self):
        for name in REQUIRED_SECRETS:
            secrets = dict(GOOD_SECRETS, **{name: ""})
            r = self.run_with(secrets)
            self.assertNotEqual(r.returncode, 0, name)
            self.assertIn(
                "::error::Secret %s is not set in the staging environment" % name, r.stdout
            )
            for other in REQUIRED_SECRETS:
                if other != name:
                    self.assertNotIn("Secret %s is not set" % other, r.stdout)
            self.assert_no_secret_printed(r, secrets)

    def test_two_missing_secrets_are_both_named(self):
        secrets = dict(GOOD_SECRETS, APP_BACKEND_URL="", APP_SIGNING_KEY_ALIAS="")
        r = self.run_with(secrets)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::Secret APP_BACKEND_URL is not set in the staging environment", r.stdout)
        self.assertIn("::error::Secret APP_SIGNING_KEY_ALIAS is not set in the staging environment", r.stdout)
        self.assert_no_secret_printed(r, secrets)

    def test_empty_token_passes(self):
        secrets = dict(GOOD_SECRETS, APP_TOKEN="")
        r = self.run_with(secrets)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_bad_url_fails_without_printing_it(self):
        for url in (
            "ftp://x",
            "x",
            "http://203.0.113.10:8000/a b",
            'http://203.0.113.10:8000/"x',
            "http://203.0.113.10:8000/'x",
            "http://203.0.113.10:8000/\\x",
            "http://203.0.113.10:8000/\nx",
            "http:///no-host",
        ):
            secrets = dict(GOOD_SECRETS, APP_BACKEND_URL=url)
            r = self.run_with(secrets)
            self.assertNotEqual(r.returncode, 0, repr(url))
            self.assertIn(self.URL_MESSAGE, r.stdout, repr(url))
            self.assert_no_secret_printed(r, secrets)

    def test_bad_token_fails_without_printing_it(self):
        for token in ('tok"x', "tok'x", "tok\\x", "tok\nx", "tok\rx"):
            secrets = dict(GOOD_SECRETS, APP_TOKEN=token)
            r = self.run_with(secrets)
            self.assertNotEqual(r.returncode, 0, repr(token))
            self.assertIn(self.TOKEN_MESSAGE, r.stdout, repr(token))
            self.assert_no_secret_printed(r, secrets)


class Version(unittest.TestCase):
    """Scenario: New build installs over the old one (the rising version number)."""

    def setUp(self):
        self.s = step(load_workflow(), "Version")

    def run_version(self, number, attempt):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            r = run_step(
                self.s["run"],
                {"RUN_NUMBER": str(number), "RUN_ATTEMPT": str(attempt), "GITHUB_OUTPUT": out},
                tmp,
            )
            values = {}
            if os.path.exists(out):
                with open(out) as fh:
                    for line in fh:
                        key, _, value = line.strip().partition("=")
                        values[key] = value
            return r, values

    def test_reads_run_number_and_attempt(self):
        self.assertEqual(self.s["env"]["RUN_NUMBER"], "${{ github.run_number }}")
        self.assertEqual(self.s["env"]["RUN_ATTEMPT"], "${{ github.run_attempt }}")
        self.assertEqual(self.s["id"], "version")

    def test_first_attempt(self):
        r, values = self.run_version(7, 1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            values,
            {
                "version_code": "701",
                "version_name": "0.1.0-staging.701",
                "apk_name": "mirror-staging-701.apk",
            },
        )

    def test_rerun_gets_its_own_number(self):
        r, values = self.run_version(7, 2)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(values["version_code"], "702")

    def test_next_run_is_higher_than_every_attempt_of_the_last(self):
        _, last = self.run_version(7, 99)
        _, nxt = self.run_version(8, 1)
        self.assertGreater(int(nxt["version_code"]), int(last["version_code"]))

    def test_attempt_above_99_fails(self):
        r, _ = self.run_version(7, 100)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::Run attempt 100 is above 99; start a new run instead", r.stdout)

    def test_job_exposes_the_version_for_publish(self):
        outputs = load_workflow()["jobs"]["build"]["outputs"]
        for key in ("version_code", "version_name", "apk_name"):
            self.assertEqual(outputs[key], "${{ steps.version.outputs.%s }}" % key)


class SigningKey(unittest.TestCase):
    """Scenario: Missing signing secret (a keystore that cannot be decoded)."""

    def setUp(self):
        self.s = step(load_workflow(), "Signing key")

    def test_reads_the_keystore_through_env(self):
        self.assertEqual(self.s["env"], {"APP_SIGNING_KEYSTORE": "${{ secrets.APP_SIGNING_KEYSTORE }}"})

    def test_decodes_to_a_private_file(self):
        raw = bytes(range(256))
        with tempfile.TemporaryDirectory() as tmp:
            r = run_step(
                self.s["run"],
                {"APP_SIGNING_KEYSTORE": base64.b64encode(raw).decode(), "RUNNER_TEMP": tmp},
                tmp,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            path = os.path.join(tmp, "staging-signing.p12")
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), raw)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_value_that_is_not_base64_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            value = "not base64 at all!!"
            r = run_step(self.s["run"], {"APP_SIGNING_KEYSTORE": value, "RUNNER_TEMP": tmp}, tmp)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("::error::Secret APP_SIGNING_KEYSTORE is not valid base64", r.stdout)
            self.assertNotIn(value, r.stdout + r.stderr)


class BuildAndApk(unittest.TestCase):
    """Scenarios: Changing the staging backend; Token switch on; Missing
    signing secret (an unsigned build fails the run)."""

    def setUp(self):
        self.wf = load_workflow()

    def test_build_passes_every_value_as_a_gradle_env_property(self):
        s = step(self.wf, "Build the staging app")
        self.assertEqual(
            s["env"],
            {
                "ORG_GRADLE_PROJECT_mirrorStagingBackendUrl": "${{ secrets.APP_BACKEND_URL }}",
                "ORG_GRADLE_PROJECT_mirrorStagingAppToken": "${{ secrets.APP_TOKEN }}",
                "ORG_GRADLE_PROJECT_mirrorStagingKeystoreFile": "${{ runner.temp }}/staging-signing.p12",
                "ORG_GRADLE_PROJECT_mirrorStagingStorePassword": "${{ secrets.APP_SIGNING_STORE_PASSWORD }}",
                "ORG_GRADLE_PROJECT_mirrorStagingKeyAlias": "${{ secrets.APP_SIGNING_KEY_ALIAS }}",
                "ORG_GRADLE_PROJECT_mirrorStagingKeyPassword": "${{ secrets.APP_SIGNING_KEY_PASSWORD }}",
                "ORG_GRADLE_PROJECT_mirrorStagingVersionCode": "${{ steps.version.outputs.version_code }}",
            },
        )
        self.assertIn("./gradlew assembleStagingRelease", s["run"])

    def test_every_gradle_variable_name_is_a_shell_identifier(self):
        # `app/gradlew` runs under /bin/sh (dash on ubuntu-latest), which
        # drops any variable whose name is not a shell identifier.
        for key in step(self.wf, "Build the staging app")["env"]:
            self.assertRegex(key, r"^[A-Za-z_][A-Za-z0-9_]*$")

    def test_every_gradle_variable_reaches_gradle_through_sh(self):
        s = step(self.wf, "Build the staging app")
        values = {key: "value-%d" % i for i, key in enumerate(s["env"])}
        shells = ["/bin/sh"] + [p for p in ("/bin/dash", "/usr/bin/dash") if os.path.exists(p)]
        for shell in shells:
            with tempfile.TemporaryDirectory() as tmp:
                os.makedirs(os.path.join(tmp, "app"))
                gradlew = os.path.join(tmp, "app", "gradlew")
                dump = os.path.join(tmp, "env.out")
                with open(gradlew, "w") as fh:
                    fh.write("#!%s\nenv > %s\n" % (shell, dump))
                os.chmod(gradlew, 0o755)
                r = run_step(s["run"], values, tmp)
                self.assertEqual(r.returncode, 0, (shell, r.stdout + r.stderr))
                with open(dump) as fh:
                    seen = dict(line.rstrip("\n").split("=", 1) for line in fh if "=" in line)
                for key, value in values.items():
                    self.assertEqual(seen.get(key), value, (shell, key))

    def test_unit_suite_is_the_gate_suite(self):
        self.assertIn("./gradlew testDevDebugUnitTest", step(self.wf, "Unit tests")["run"])

    def test_toolchain(self):
        jdk = step(self.wf, "Set up JDK")
        self.assertTrue(jdk["uses"].startswith("actions/setup-java@"))
        self.assertEqual(jdk["with"], {"distribution": "temurin", "java-version": "21"})
        self.assertTrue(step(self.wf, "Set up Android SDK")["uses"].startswith("android-actions/setup-android@"))
        self.assertTrue(step(self.wf, "Set up Gradle")["uses"].startswith("gradle/actions/setup-gradle@"))

    def test_apk_signed_fails_without_the_signed_apk(self):
        s = step(self.wf, "APK signed")
        with tempfile.TemporaryDirectory() as tmp:
            r = run_step(s["run"], {"APK_NAME": "mirror-staging-701.apk", "RUNNER_TEMP": tmp}, tmp)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("::error::The staging APK was not signed", r.stdout)

    def test_apk_signed_fails_with_only_an_unsigned_apk(self):
        s = step(self.wf, "APK signed")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "app/app/build/outputs/apk/staging/release")
            os.makedirs(out)
            open(os.path.join(out, "app-staging-release-unsigned.apk"), "w").close()
            r = run_step(s["run"], {"APK_NAME": "mirror-staging-701.apk", "RUNNER_TEMP": tmp}, tmp)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("::error::The staging APK was not signed", r.stdout)

    def test_apk_signed_copies_the_apk(self):
        s = step(self.wf, "APK signed")
        self.assertEqual(s["env"]["APK_NAME"], "${{ steps.version.outputs.apk_name }}")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "app/app/build/outputs/apk/staging/release")
            os.makedirs(out)
            with open(os.path.join(out, "app-staging-release.apk"), "wb") as fh:
                fh.write(b"apk-bytes")
            r = run_step(s["run"], {"APK_NAME": "mirror-staging-701.apk", "RUNNER_TEMP": tmp}, tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(os.path.join(tmp, "mirror-staging-701.apk"), "rb") as fh:
                self.assertEqual(fh.read(), b"apk-bytes")

    def test_apk_is_kept_for_the_publish_job(self):
        s = step(self.wf, "Keep the APK")
        self.assertTrue(s["uses"].startswith("actions/upload-artifact@"))
        self.assertEqual(s["with"]["name"], "staging-apk")
        self.assertEqual(s["with"]["path"], "${{ runner.temp }}/${{ steps.version.outputs.apk_name }}")
        self.assertEqual(s["with"]["retention-days"], 1)
        self.assertEqual(s["with"]["if-no-files-found"], "error")

    def test_clean_up_removes_the_key(self):
        s = step(self.wf, "Clean up")
        with tempfile.TemporaryDirectory() as tmp:
            key = os.path.join(tmp, "staging-signing.p12")
            open(key, "w").close()
            r = run_step(s["run"], {"RUNNER_TEMP": tmp}, tmp)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(os.path.exists(key))

    def test_job_reads_the_staging_environment(self):
        job = self.wf["jobs"]["build"]
        self.assertEqual(job["environment"], "staging")
        self.assertEqual(job["permissions"], {"contents": "read"})
        self.assertEqual(self.wf["permissions"], {"contents": "read"})


class StepOrder(unittest.TestCase):
    def test_step_order(self):
        steps = load_workflow()["jobs"]["build"]["steps"]
        self.assertEqual([s.get("name") for s in steps], STEP_ORDER)


class SecretsStayOutOfTheLog(unittest.TestCase):
    """Scenario: Build log and notes (the log)."""

    def setUp(self):
        self.wf = load_workflow()
        self.steps = self.wf["jobs"]["build"]["steps"]

    def test_secrets_reach_steps_through_env_only(self):
        for s in self.steps:
            self.assertNotIn("secrets.", s.get("run", ""), s.get("name"))
            self.assertNotIn("secrets.", yaml.safe_dump(s.get("with", {})), s.get("name"))

    def test_build_step_uses_only_gradle_env_properties(self):
        s = step(self.wf, "Build the staging app")
        for key in s["env"]:
            self.assertTrue(key.startswith("ORG_GRADLE_PROJECT_"), key)
        for flag in ("-P", "--info", "--debug", "--scan", "--stacktrace"):
            self.assertNotIn(flag, s["run"])

    def test_no_gradle_call_uses_verbose_flags(self):
        for s in self.steps:
            run = s.get("run", "")
            if "gradlew" in run:
                for flag in ("-P", "--info", "--debug", "--scan", "--stacktrace"):
                    self.assertNotIn(flag, run, s.get("name"))

    def test_no_step_traces_commands(self):
        for s in self.steps:
            self.assertNotRegex(s.get("run", ""), r"set\s+-[a-wyz]*x", s.get("name"))


class FailuresStopTheRun(unittest.TestCase):
    """Scenario: Failed build publishes nothing (the build job fails)."""

    def setUp(self):
        self.wf = load_workflow()
        self.job = self.wf["jobs"]["build"]

    def test_only_clean_up_has_a_condition(self):
        for s in self.job["steps"]:
            if s.get("name") == "Clean up":
                self.assertEqual(s["if"], "always()")
            else:
                self.assertNotIn("if", s, s.get("name"))

    def test_nothing_swallows_a_failure(self):
        for name, job in self.wf["jobs"].items():
            self.assertNotIn("continue-on-error", job, name)
            for s in job.get("steps", []):
                self.assertNotIn("continue-on-error", s, (name, s.get("name")))

    def test_every_shell_step_parses(self):
        for s in self.job["steps"]:
            if "run" in s:
                r = subprocess.run(["bash", "-n", "-c", s["run"]], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, (s.get("name"), r.stderr))

    def test_one_build_at_a_time(self):
        self.assertEqual(
            self.wf["concurrency"], {"group": "staging-app", "cancel-in-progress": False}
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
