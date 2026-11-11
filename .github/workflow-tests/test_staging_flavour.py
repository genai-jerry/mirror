"""Tests for the staging flavour of the app (epic #61, task #66).

These build the app for real with Gradle, so they need a JDK (21 or later)
and an Android SDK, found the way scripts/gate.sh finds them (ANDROID_HOME,
ANDROID_SDK_ROOT, ~/Android/Sdk or app/local.properties). Without them every
test is skipped, unless MIRROR_APP_GATE=required, which makes a missing SDK a
failure, exactly as in the gate.

They pass every value the way the "Staging app" workflow does, as
ORG_GRADLE_PROJECT_<name> environment variables, and then read the APK
Gradle produced:

* the backend address and app token the build was given are the ones in
  BuildConfig and in the APK's code;
* a second build with a different address and a higher version number
  carries the new address, a higher version code, the same package name
  and the same signing certificate, so it installs over the first, and no
  file in the repository changed between the two;
* the dev and systemTest flavours keep their app id, version, address and
  token, even with every staging value set;
* the staging build's network rule allows plain HTTP to the host of the
  address it was given and to nothing else, and a changed address changes
  the rule; dev and systemTest keep the local addresses only (task #67);
* a bad address stops the build without printing the address;
* without the signing values the staging release build is unsigned (the
  workflow's `APK signed` step then fails the run).

Every value is synthetic: documentation addresses (RFC 5737), made-up
tokens and a key made for this run and deleted after it.

Run: python3 .github/workflow-tests/test_staging_flavour.py
"""

import glob
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
APP = os.path.join(ROOT, "app")
MODULE_BUILD = os.path.join(APP, "app", "build")

FIRST = {
    "url": "http://198.51.100.7:8000/",
    "token": "tok-synthetic-first-5d1a",
    "version": 41,
}
SECOND = {
    "url": "https://staging-two.example.test/api/",
    "token": "tok-synthetic-second-9c3e",
    "version": 42,
}
STORE_PASSWORD = "store-pw-synthetic-qa"
KEY_PASSWORD = "store-pw-synthetic-qa"  # PKCS12 uses one password for both
KEY_ALIAS = "alias-synthetic-qa"

# The plain-HTTP hosts of the dev and systemTest builds, in the main file's order.
LOCAL_HOSTS = ["127.0.0.1", "localhost", "10.0.2.2"]

DEV = {
    "package": "com.genaijerry.mirror",
    "version_code": "1",
    "version_name": "0.1.0",
    "url": "http://10.0.2.2:8000/",
    "token": "",
}
SYSTEM_TEST = {
    "package": "com.genaijerry.mirror.systemtest",
    "version_code": "1",
    "version_name": "0.1.0-systemtest",
    "url": "http://127.0.0.1:8000/",
    "token": "",
}


def android_sdk_dir():
    for candidate in (
        os.environ.get("ANDROID_HOME"),
        os.environ.get("ANDROID_SDK_ROOT"),
        os.path.expanduser("~/Android/Sdk"),
    ):
        if candidate and os.path.isdir(os.path.join(candidate, "platforms")):
            return candidate
    local = os.path.join(APP, "local.properties")
    if os.path.isfile(local):
        with open(local) as handle:
            for line in handle:
                if line.startswith("sdk.dir="):
                    candidate = line.split("=", 1)[1].strip()
                    if os.path.isdir(os.path.join(candidate, "platforms")):
                        return candidate
    return None


SDK = android_sdk_dir()
HAVE_TOOLS = SDK is not None and shutil.which("java") is not None and shutil.which("keytool")
if not HAVE_TOOLS and os.environ.get("MIRROR_APP_GATE") == "required":
    raise SystemExit("No JDK or Android SDK, and MIRROR_APP_GATE=required.")


def build_tool(name):
    found = sorted(glob.glob(os.path.join(SDK, "build-tools", "*", name)))
    if not found:
        raise AssertionError(f"No {name} in {SDK}/build-tools")
    return found[-1]


def gradle(tasks, properties):
    """Run Gradle in app/ with the staging values as ORG_GRADLE_PROJECT_* only."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("ORG_GRADLE_PROJECT_")}
    for name, value in properties.items():
        env[f"ORG_GRADLE_PROJECT_{name}"] = value
    return subprocess.run(
        ["./gradlew", "--quiet", *tasks],
        cwd=APP,
        env=env,
        capture_output=True,
        text=True,
    )


def staging_properties(values, keystore):
    properties = {
        "mirrorStagingBackendUrl": values["url"],
        "mirrorStagingAppToken": values["token"],
        "mirrorStagingVersionCode": str(values["version"]),
    }
    if keystore:
        properties.update(
            {
                "mirrorStagingKeystoreFile": keystore,
                "mirrorStagingStorePassword": STORE_PASSWORD,
                "mirrorStagingKeyAlias": KEY_ALIAS,
                "mirrorStagingKeyPassword": KEY_PASSWORD,
            }
        )
    return properties


def build_config(flavour, build_type):
    path = os.path.join(
        MODULE_BUILD,
        "generated",
        "source",
        "buildConfig",
        flavour,
        build_type,
        "com",
        "genaijerry",
        "mirror",
        "BuildConfig.java",
    )
    with open(path) as handle:
        source = handle.read()
    return dict(re.findall(r'public static final String (\w+) = "(.*)";', source))


def badging(apk):
    out = subprocess.run(
        [build_tool("aapt2"), "dump", "badging", apk],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    line = out.splitlines()[0]
    return dict(re.findall(r"(\w+)='([^']*)'", line))


def network_rule(apk):
    """The APK's plain-HTTP rule: (base config allows it, [hosts it is allowed to]).

    Follows the manifest's android:networkSecurityConfig to the packaged file,
    so this reads the rule the phone reads, whichever file that is.
    """
    aapt2 = build_tool("aapt2")

    def dump(*args):
        return subprocess.run(
            [aapt2, "dump", *args, apk], capture_output=True, text=True, check=True
        ).stdout

    manifest = dump("xmltree", "--file", "AndroidManifest.xml")
    resource_id = re.search(r":networkSecurityConfig\(0x[0-9a-f]+\)=@(0x[0-9a-f]+)", manifest)
    resources = dump("resources")
    path = re.search(
        rf"resource {resource_id.group(1)} \S+\n\s+\(\) \(file\) (\S+)", resources
    ).group(1)
    tree = dump("xmltree", "--file", path)
    base = re.search(r"E: base-config.*\n\s+A: cleartextTrafficPermitted=(\w+)", tree)
    hosts = []
    for block in re.split(r"\n\s+E: domain-config", tree)[1:]:
        if re.match(r"[^\n]*\n\s+A: cleartextTrafficPermitted=true", block):
            hosts += re.findall(r"T: '([^']*)'", block)
    return base.group(1) == "true", hosts


def signer_digest(apk):
    result = subprocess.run(
        [build_tool("apksigner"), "verify", "--print-certs", apk],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    match = re.search(r"certificate SHA-256 digest: ([0-9a-f]+)", result.stdout)
    return match.group(1) if match else None


def dex_contains(apk, text):
    needle = text.encode()
    with zipfile.ZipFile(apk) as archive:
        return any(
            needle in archive.read(name)
            for name in archive.namelist()
            if name.endswith(".dex")
        )


def tracked_changes():
    return subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@unittest.skipUnless(HAVE_TOOLS, "needs a JDK and an Android SDK (see the module docstring)")
class StagingFlavourBuilds(unittest.TestCase):
    """Two signed staging builds, the way two workflow runs make them."""

    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp(prefix="staging-flavour-")
        cls.keystore = os.path.join(cls.work, "test-key.p12")
        subprocess.run(
            [
                "keytool", "-genkeypair", "-keystore", cls.keystore, "-storetype", "pkcs12",
                "-storepass", STORE_PASSWORD, "-keypass", KEY_PASSWORD, "-alias", KEY_ALIAS,
                "-keyalg", "RSA", "-keysize", "2048", "-validity", "2",
                "-dname", "CN=Synthetic QA key",
            ],
            check=True,
            capture_output=True,
        )
        cls.files_before = tracked_changes()
        cls.builds = {}
        for label, values, tasks in (
            ("first", FIRST, ["assembleStagingRelease", "assembleDevDebug", "assembleSystemTestDebug"]),
            ("second", SECOND, ["assembleStagingRelease"]),
        ):
            result = gradle(tasks, staging_properties(values, cls.keystore))
            if result.returncode != 0:
                raise AssertionError(f"{label} build failed:\n{result.stdout}\n{result.stderr}")
            apk = os.path.join(cls.work, f"staging-{label}.apk")
            shutil.copy(
                os.path.join(MODULE_BUILD, "outputs", "apk", "staging", "release", "app-staging-release.apk"),
                apk,
            )
            cls.builds[label] = {
                "apk": apk,
                "config": build_config("staging", "release"),
                "log": result.stdout + result.stderr,
            }
            if label == "first":
                for flavour in ("dev", "systemTest"):
                    copy = os.path.join(cls.work, f"{flavour}-debug.apk")
                    shutil.copy(
                        os.path.join(MODULE_BUILD, "outputs", "apk", flavour, "debug", f"app-{flavour}-debug.apk"),
                        copy,
                    )
                    cls.builds[flavour] = {"apk": copy, "config": build_config(flavour, "debug")}
        cls.files_after = tracked_changes()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    # Scenario: App reaches the staging backend
    def test_the_staging_build_talks_to_the_address_it_was_given(self):
        first = self.builds["first"]
        self.assertEqual(first["config"]["BACKEND_BASE_URL"], FIRST["url"])
        self.assertTrue(dex_contains(first["apk"], FIRST["url"]))

    # Scenario: Changing the staging backend
    def test_a_changed_address_changes_the_next_build(self):
        second = self.builds["second"]
        self.assertEqual(second["config"]["BACKEND_BASE_URL"], SECOND["url"])
        self.assertTrue(dex_contains(second["apk"], SECOND["url"]))
        self.assertFalse(dex_contains(second["apk"], FIRST["url"]))

    # Scenarios: Plain HTTP staging backend, Any other plain HTTP server
    def test_the_staging_build_allows_plain_http_to_its_backend_host_only(self):
        self.assertEqual(network_rule(self.builds["first"]["apk"]), (False, ["198.51.100.7"]))

    def test_a_changed_address_changes_the_plain_http_host(self):
        self.assertEqual(
            network_rule(self.builds["second"]["apk"]), (False, ["staging-two.example.test"])
        )

    def test_changing_the_address_changes_no_file_in_the_repository(self):
        self.assertEqual(self.files_before, self.files_after)

    # Scenario: Token switch on
    def test_the_staging_build_carries_the_token_it_was_given(self):
        self.assertEqual(self.builds["first"]["config"]["BACKEND_APP_TOKEN"], FIRST["token"])
        self.assertEqual(self.builds["second"]["config"]["BACKEND_APP_TOKEN"], SECOND["token"])

    # Scenario: New build installs over the old one
    def test_both_builds_are_the_staging_app(self):
        for label in ("first", "second"):
            self.assertEqual(
                badging(self.builds[label]["apk"])["name"], "com.genaijerry.mirror.staging"
            )

    def test_the_version_is_the_one_given_and_rises(self):
        first = badging(self.builds["first"]["apk"])
        second = badging(self.builds["second"]["apk"])
        self.assertEqual(first["versionCode"], "41")
        self.assertEqual(first["versionName"], "0.1.0-staging.41")
        self.assertEqual(second["versionCode"], "42")
        self.assertEqual(second["versionName"], "0.1.0-staging.42")
        self.assertGreater(int(second["versionCode"]), int(first["versionCode"]))

    def test_both_builds_are_signed_with_the_same_test_key(self):
        first = signer_digest(self.builds["first"]["apk"])
        second = signer_digest(self.builds["second"]["apk"])
        self.assertIsNotNone(first)
        self.assertEqual(first, second)

    def test_the_build_log_shows_no_secret_value(self):
        for label, values in (("first", FIRST), ("second", SECOND)):
            log = self.builds[label]["log"]
            for secret in (values["url"], values["token"], STORE_PASSWORD):
                self.assertNotIn(secret, log)

    # Scenario: Other builds unchanged (the flavours)
    def test_dev_is_unchanged_with_every_staging_value_set(self):
        self.assert_unchanged("dev", DEV)

    def test_system_test_is_unchanged_with_every_staging_value_set(self):
        self.assert_unchanged("systemTest", SYSTEM_TEST)

    def assert_unchanged(self, flavour, expected):
        build = self.builds[flavour]
        info = badging(build["apk"])
        self.assertEqual(info["name"], expected["package"])
        self.assertEqual(info["versionCode"], expected["version_code"])
        self.assertEqual(info["versionName"], expected["version_name"])
        self.assertEqual(build["config"]["BACKEND_BASE_URL"], expected["url"])
        self.assertEqual(build["config"]["BACKEND_APP_TOKEN"], expected["token"])
        # Scenario: Other builds unchanged (the network rules)
        self.assertEqual(network_rule(build["apk"]), (False, LOCAL_HOSTS))


@unittest.skipUnless(HAVE_TOOLS, "needs a JDK and an Android SDK (see the module docstring)")
class StagingFlavourRefusals(unittest.TestCase):
    def test_a_bad_address_stops_the_build_without_printing_it(self):
        bad = "ftp://198.51.100.9/never-printed"
        result = gradle(["help"], {"mirrorStagingBackendUrl": bad})
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("mirrorStagingBackendUrl is not an http or https URL", output)
        self.assertNotIn(bad, output)

    def test_without_the_signing_values_the_release_build_is_unsigned(self):
        out_dir = os.path.join(MODULE_BUILD, "outputs", "apk", "staging", "release")
        shutil.rmtree(out_dir, ignore_errors=True)
        result = gradle(["assembleStagingRelease"], staging_properties(FIRST, keystore=None))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(os.path.exists(os.path.join(out_dir, "app-staging-release.apk")))
        unsigned = os.path.join(out_dir, "app-staging-release-unsigned.apk")
        self.assertTrue(os.path.isfile(unsigned))
        self.assertIsNone(signer_digest(unsigned))


if __name__ == "__main__":
    unittest.main(verbosity=2)
