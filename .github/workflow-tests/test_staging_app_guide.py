"""Tests for the staging app guide, docs/staging-app.md (epic #61, task #68).

The guide must let an owner set up the build and a tester install the app
without reading the workflow (design.md, Task 5). These tests read the names
and messages from .github/workflows/staging-app.yml and compare them with the
guide, so a secret or an error message added to the workflow without a line
in the guide fails here:

* the secrets table lists exactly the `secrets.` names the workflow reads,
  except the run's own GITHUB_TOKEN, and marks as required exactly the ones
  the workflow refuses to run without;
* every `::error::` message the workflow prints is in the guide;
* the guide covers making the key, the manual run, the pre-release and the
  install, including a newer build over an older one;
* the README links the guide;
* the guide holds placeholders only, no real address or key.

Scenarios served (staging-app-distribution spec): Owner sets up the build,
Tester installs the app.

Run: python3 .github/workflow-tests/test_staging_app_guide.py
Needs Python 3 only.
"""

import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GUIDE = os.path.join(ROOT, "docs", "staging-app.md")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "staging-app.yml")
README = os.path.join(ROOT, "README.md")

# Provided by GitHub to every run; a person never sets it.
AUTOMATIC_SECRETS = {"GITHUB_TOKEN"}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def section(text, heading):
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def workflow_secrets():
    return set(re.findall(r"\bsecrets\.([A-Za-z0-9_]+)", read(WORKFLOW)))


def required_by_workflow():
    """Names the build refuses to run without: the `for name in ...` loop
    whose body reports "<name> is not set"."""
    m = re.search(
        r"for name in ([A-Z0-9_ ]+); do\n(?:[^\n]*\n){0,3}?[^\n]*is not set", read(WORKFLOW)
    )
    if not m:
        raise AssertionError("no required-settings check found in the workflow")
    return set(m.group(1).split())


def workflow_errors():
    return re.findall(r"::error::([^\"\n]+)\"", read(WORKFLOW))


def secrets_table():
    """Rows of the secrets table: name -> list of cells."""
    rows = {}
    for line in section(read(GUIDE), "## 2. Secrets").splitlines():
        m = re.match(r"^\|\s*`([A-Z0-9_]+)`\s*\|(.*)\|\s*$", line)
        if m:
            rows[m.group(1)] = [c.strip() for c in m.group(2).split("|")]
    return rows


class Secrets(unittest.TestCase):
    """Owner sets up the build: every secret, named, required or optional."""

    @classmethod
    def setUpClass(cls):
        cls.rows = secrets_table()

    def test_table_lists_every_workflow_secret_and_no_other(self):
        expected = workflow_secrets() - AUTOMATIC_SECRETS
        self.assertTrue(expected, "found no secrets in the workflow")
        self.assertEqual(set(self.rows), expected)

    def test_each_row_says_required_or_optional_and_what_it_holds(self):
        for name, cells in self.rows.items():
            self.assertEqual(len(cells), 2, name)
            required, holds = cells
            self.assertTrue(required.startswith(("required", "optional")), name)
            self.assertGreater(len(holds), 20, name)

    def test_required_matches_the_workflows_check(self):
        required = required_by_workflow()
        self.assertIn("APP_BACKEND_URL", required)
        self.assertLessEqual(required, set(self.rows))
        for name, cells in self.rows.items():
            want = "required" if name in required else "optional"
            self.assertTrue(cells[0].startswith(want), f"{name}: {cells[0]}")

    def test_secrets_live_in_the_staging_environment(self):
        text = section(read(GUIDE), "## 2. Secrets")
        self.assertIn("Settings → Environments → `staging`", text)
        self.assertIn("environment: staging", read(WORKFLOW))


class MakingTheKey(unittest.TestCase):
    """Owner sets up the build: the test signing key and its secrets."""

    def test_names_the_keytool_and_base64_commands(self):
        text = section(read(GUIDE), "## 3. Making the test signing key")
        for needed in (
            "keytool -genkeypair -storetype PKCS12",
            "-alias mirror-staging",
            "base64 -w0",
            "APP_SIGNING_KEYSTORE",
            "password manager",
        ):
            self.assertIn(needed, text)

    def test_alias_in_the_command_matches_the_alias_secret(self):
        text = read(GUIDE)
        alias = re.search(r"-alias (\S+)", text).group(1)
        self.assertIn(f"`{alias}` → `APP_SIGNING_KEY_ALIAS`", text)


class FirstBuild(unittest.TestCase):
    """Owner sets up the build: run it by hand and find the pre-release."""

    @classmethod
    def setUpClass(cls):
        cls.text = section(read(GUIDE), "## 4. The first build")

    def test_manual_run_on_staging(self):
        self.assertIn("Actions → **Staging app** → **Run workflow**", self.text)
        self.assertIn("choose `staging`", self.text)

    def test_names_the_workflow_and_its_jobs_as_github_shows_them(self):
        workflow = read(WORKFLOW)
        self.assertIn("name: Staging app\n", workflow)
        for job in ("Build and sign the staging app", "Publish the staging pre-release"):
            self.assertIn(f"name: {job}", workflow)
            self.assertIn(job, self.text)

    def test_says_where_the_pre_release_appears(self):
        for needed in ("Releases", "Pre-release", "Mirror staging 0.1.0-staging.", "mirror-staging-"):
            self.assertIn(needed, self.text)
        workflow = read(WORKFLOW)
        self.assertIn('--title "Mirror staging ${VERSION_NAME}"', workflow)
        self.assertIn('version_name=0.1.0-staging.', workflow)
        self.assertIn('apk_name=mirror-staging-', workflow)

    def test_every_workflow_error_is_explained(self):
        errors = workflow_errors()
        self.assertGreaterEqual(len(errors), 8, errors)
        for message in errors:
            for fragment in re.split(r"\$\{[^}]+\}", message):
                fragment = fragment.strip()
                if len(fragment) > 3:
                    self.assertIn(fragment, self.text, message)


class Installing(unittest.TestCase):
    """Tester installs the app, and a newer build over an older one."""

    @classmethod
    def setUpClass(cls):
        cls.text = section(read(GUIDE), "## 5. Installing the app on a phone")

    def test_steps_from_sign_in_to_open(self):
        for needed in (
            "Sign in to GitHub",
            "newest pre-release",
            "Assets",
            ".apk",
            "Allow from this source",
            "Install",
            "Mirror staging",
        ):
            self.assertIn(needed, self.text)

    def test_newer_build_installs_as_an_update(self):
        self.assertIn("Installing a newer build", self.text)
        self.assertIn("Do not uninstall the old build first", self.text)
        self.assertIn("**Update**", self.text)

    def test_app_name_matches_the_staging_flavour(self):
        strings = read(os.path.join(ROOT, "app", "app", "src", "staging", "res", "values", "strings.xml"))
        self.assertIn('<string name="app_name">Mirror staging</string>', strings)


class Readme(unittest.TestCase):
    def test_readme_links_the_guide(self):
        self.assertIn("(docs/staging-app.md)", read(README))

    def test_pre_release_notes_name_the_guide(self):
        self.assertIn("docs/staging-app.md", read(WORKFLOW))


class NothingReal(unittest.TestCase):
    """The guide holds placeholders only."""

    def test_no_private_key_or_real_address(self):
        text = read(GUIDE)
        self.assertNotIn("PRIVATE KEY-----", text)
        self.assertIsNone(re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text))
        for host in re.findall(r"\b[a-z0-9.-]+\.(?:com|net|org|io|in)\b", text):
            self.assertTrue(host.endswith("example.com") or host == "github.com", host)


if __name__ == "__main__":
    unittest.main()
