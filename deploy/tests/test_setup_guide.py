"""Tests for the deployment setup guide, docs/deployment.md
(openspec/changes/37-backend-deployment, Task 4).

Run from the repository root:
    python3 -m unittest discover -s deploy/tests -v

The guide must list exactly the secrets and variables the deployment reads
(design D7, D8): every `secrets.` and `vars.` name in the workflow, and no
other. These tests read the names from the workflow and the Compose file and
compare them with the guide's table, so a new secret added to the workflow
without a line in the guide fails here.

Scenarios served (backend-deployment spec): Complete list of secrets and
variables, Preparing a server.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "deployment.md"
WORKFLOW = ROOT / ".github" / "workflows" / "backend-deploy.yml"
COMPOSE = ROOT / "deploy" / "compose.yaml"
README = ROOT / "README.md"

# Provided by GitHub to every run; a person never sets it.
AUTOMATIC_SECRETS = {"GITHUB_TOKEN"}
# Written into the server's .env by the deploy job itself, not by a person.
WRITTEN_BY_DEPLOY = {"BACKEND_IMAGE"}


def required_by_workflow():
    """Names the deploy job refuses to run without: the `for name in ...`
    loop whose body reports "<name> is not set"."""
    text = WORKFLOW.read_text()
    m = re.search(r"for name in ([A-Z0-9_ ]+); do\n(?:[^\n]*\n){0,3}?[^\n]*is not set", text)
    if not m:
        raise AssertionError("no required-settings check found in the workflow")
    return set(m.group(1).split())


def guide_text():
    return GUIDE.read_text()


def guide_table():
    """Rows of the secrets-and-variables table: name -> list of cells."""
    text = guide_text()
    section = text.split("## 2. Secrets and variables", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        m = re.match(r"^\|\s*`([A-Z0-9_]+)`\s*\|(.*)\|\s*$", line)
        if m:
            rows[m.group(1)] = [c.strip() for c in m.group(2).split("|")]
    return rows


def workflow_names(prefix):
    text = WORKFLOW.read_text()
    return set(re.findall(r"\b" + prefix + r"\.([A-Za-z0-9_]+)", text))


class SecretsAndVariables(unittest.TestCase):
    """Complete list of secrets and variables."""

    @classmethod
    def setUpClass(cls):
        cls.rows = guide_table()

    def test_table_lists_every_workflow_secret_and_variable_and_no_other(self):
        expected = (workflow_names("secrets") - AUTOMATIC_SECRETS) | workflow_names("vars")
        self.assertTrue(expected, "found no secrets in the workflow")
        self.assertEqual(set(self.rows), expected)

    def test_kind_matches_the_workflow(self):
        for name in workflow_names("secrets") - AUTOMATIC_SECRETS:
            self.assertEqual(self.rows[name][0], "secret", name)
        for name in workflow_names("vars"):
            self.assertEqual(self.rows[name][0], "variable", name)

    def test_every_compose_setting_is_listed(self):
        names = set(re.findall(r"\$\{([A-Z0-9_]+)", COMPOSE.read_text()))
        self.assertTrue(names)
        for name in names - WRITTEN_BY_DEPLOY:
            self.assertIn(name, self.rows)

    def test_each_row_names_environment_requirement_and_purpose(self):
        for name, cells in self.rows.items():
            self.assertEqual(len(cells), 4, name)
            kind, environment, required, purpose = cells
            self.assertIn("`staging`", environment, name)
            self.assertIn("`production`", environment, name)
            self.assertTrue(required.startswith(("required", "optional")), name)
            self.assertGreater(len(purpose), 10, name)

    def test_required_matches_the_deploy_jobs_check(self):
        required = required_by_workflow()
        self.assertIn("SARVAM_API_KEY", required)
        self.assertLessEqual(required, set(self.rows))
        for name, cells in self.rows.items():
            want = "required" if name in required else "optional"
            self.assertTrue(cells[2].startswith(want), f"{name}: {cells[2]}")

    def test_optional_settings_name_their_default(self):
        self.assertIn("`22`", self.rows["DEPLOY_PORT"][2])
        self.assertIn("`/opt/mirror`", self.rows["DEPLOY_DIR"][2])


class PreparingAServer(unittest.TestCase):
    """Preparing a server."""

    @classmethod
    def setUpClass(cls):
        cls.text = guide_text()

    def test_names_what_to_install(self):
        for needed in ("Docker Engine", "docker compose version", "curl", "bash"):
            self.assertIn(needed, self.text)

    def test_creates_and_authorises_the_ssh_key(self):
        for needed in ("ssh-keygen -t ed25519", "authorized_keys", "ssh-keyscan", "usermod -aG docker"):
            self.assertIn(needed, self.text)

    def test_first_deploy_by_hand_and_health_check(self):
        self.assertIn("Run workflow", self.text)
        self.assertIn("/healthz", self.text)
        self.assertIn('{"status":"ok"}', self.text)

    def test_readme_links_to_the_guide(self):
        self.assertIn("docs/deployment.md", README.read_text())


class NothingReal(unittest.TestCase):
    """Secrets stay out of sight: the guide holds placeholders only."""

    def test_no_private_key_or_real_address(self):
        text = guide_text()
        self.assertNotIn("PRIVATE KEY-----", text)
        self.assertIsNone(re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text.replace("127.0.0.1", "")))
        for host in re.findall(r"\b[a-z0-9.-]+\.(?:com|net|org|io|in)\b", text):
            self.assertTrue(host.endswith("example.com") or host in ("docs.docker.com", "ghcr.io"), host)


if __name__ == "__main__":
    unittest.main()
