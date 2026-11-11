"""Tests for the deploy job and deploy/remote-deploy.sh
(openspec/changes/37-backend-deployment, Task 3).

Run from the repository root:
    python3 -m unittest discover -s deploy/tests -v

Needs PyYAML and bash. No Docker, SSH or server is used: the workflow is read
as YAML, its settings check is run in bash, and the server script runs against
fake `docker` and `curl` commands that record what they were asked to do.

Scenarios served (backend-deployment spec): Push to staging, Push to main,
Manual run (the deploy), Changing a server, Missing secret, Required key
missing, Settings reach the container, Secrets stay out of sight, Redeploy
keeps configuration, Redeploy replaces the old container, Healthy deploy,
Unhealthy deploy, Two pushes in quick succession.
"""

import os
import pathlib
import stat
import subprocess
import tempfile
import textwrap
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "backend-deploy.yml"
SCRIPT = ROOT / "deploy" / "remote-deploy.sh"
ENV_EXPR = "${{ github.ref_name == 'main' && 'production' || 'staging' }}"
REQUIRED = [
    "DEPLOY_HOST",
    "DEPLOY_USER",
    "DEPLOY_SSH_KEY",
    "DEPLOY_KNOWN_HOSTS",
    "SARVAM_API_KEY",
]


def load_workflow():
    return yaml.safe_load(WORKFLOW.read_text())


class DeployJobStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load_workflow()
        cls.job = cls.doc["jobs"]["deploy"]
        cls.steps = cls.job["steps"]
        cls.names = [s["name"] for s in cls.steps]

    def step(self, name):
        return self.steps[self.names.index(name)]

    def test_runs_only_after_build(self):
        # Image published before deploy / Build fails: no server after a failed build.
        self.assertEqual(self.job["needs"], "build")

    def test_branch_maps_to_environment(self):
        # Push to staging / Push to main: each branch reaches only its own server.
        self.assertEqual(self.job["environment"], ENV_EXPR)
        self.assertEqual(self.job["env"]["ENVIRONMENT"], ENV_EXPR)

    def test_deploys_queue_per_environment(self):
        # Two pushes in quick succession: queued, never cancelled.
        self.assertEqual(
            self.job["concurrency"],
            {"group": f"backend-deploy-{ENV_EXPR}", "cancel-in-progress": False},
        )

    def test_least_permissions(self):
        self.assertEqual(self.job["permissions"], {"contents": "read", "packages": "read"})

    def test_deploys_the_published_image(self):
        self.assertEqual(self.job["env"]["IMAGE"], "${{ needs.build.outputs.image }}")

    def test_settings_checked_before_any_server_contact(self):
        first = self.steps[0]
        self.assertEqual(first["name"], "Required settings present")
        for name in REQUIRED:
            self.assertEqual(first["env"][name], "${{ secrets.%s }}" % name)
        before = "".join(s.get("run", "") for s in self.steps[: self.names.index("Copy files to the server")])
        self.assertNotIn("ssh deploy-server", before)
        self.assertNotRegex(before, r"(?m)^\s*scp ")

    def test_server_comes_from_secrets_only(self):
        # Changing a server: the address lives in a secret, not in a file.
        setup = self.step("SSH set-up")
        self.assertEqual(setup["env"]["DEPLOY_HOST"], "${{ secrets.DEPLOY_HOST }}")
        self.assertEqual(setup["env"]["DEPLOY_PORT"], "${{ secrets.DEPLOY_PORT }}")
        self.assertIn("StrictHostKeyChecking yes", setup["run"])
        self.assertIn("BatchMode yes", setup["run"])
        self.assertIn("Port ${DEPLOY_PORT:-22}", setup["run"])

    def test_env_file_written_through_stdin(self):
        run = self.step("Write the server's .env")["run"]
        self.assertIn("umask 077; cat >", run)
        for name in ["BACKEND_IMAGE", "SARVAM_API_KEY", "ADMIN_TOKEN", "APP_TOKEN"]:
            self.assertIn(f"{name}=", run)

    def test_token_on_stdin_only(self):
        step = self.step("Deploy and check health")
        self.assertEqual(step["env"]["REGISTRY_TOKEN"], "${{ secrets.GITHUB_TOKEN }}")
        self.assertIn('printf \'%s\\n\' "$REGISTRY_TOKEN"', step["run"])
        self.assertIn("remote-deploy.sh", step["run"])

    def test_summary_names_environment_and_image(self):
        # Healthy deploy / Unhealthy deploy.
        self.assertIn("Deployed ${IMAGE} to ${ENVIRONMENT}", self.step("Summary")["run"])
        failed = self.step("Report a failed deploy")
        self.assertEqual(failed["if"], "failure()")
        self.assertIn("::error::Deploy of", failed["run"])
        self.assertIn("to ${ENVIRONMENT} failed", failed["run"])

    def test_key_removed_whatever_happens(self):
        last = self.steps[-1]
        self.assertEqual(last["if"], "always()")
        self.assertIn("~/.ssh/deploy_key", last["run"])

    def test_no_trace_and_no_secret_interpolated_into_shell(self):
        # Secrets stay out of sight: secrets reach shell only through env.
        for step in self.steps:
            run = step.get("run", "")
            self.assertNotIn("set -x", run)
            self.assertNotIn("${{", run, f"expression in shell of {step['name']!r}")
        self.assertNotRegex(SCRIPT.read_text(), r"(?m)^\s*set -[a-z]*x")


class RequiredSettingsCheck(unittest.TestCase):
    """The first step's shell, run as GitHub would run it."""

    @classmethod
    def setUpClass(cls):
        cls.run_script = load_workflow()["jobs"]["deploy"]["steps"][0]["run"]

    def run_check(self, **overrides):
        env = {"PATH": os.environ["PATH"], "ENVIRONMENT": "staging",
               "IMAGE": "ghcr.io/example/mirror-backend:abc123"}
        env.update({name: f"value-of-{name.lower()}" for name in REQUIRED})
        env.update(overrides)
        return subprocess.run(["bash", "-e", "-c", self.run_script],
                              capture_output=True, text=True, env=env)

    def test_all_set_passes(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_missing_sarvam_key_is_named(self):
        result = self.run_check(SARVAM_API_KEY="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::error::Secret SARVAM_API_KEY is not set in the staging environment", result.stdout)

    def test_every_missing_secret_is_named(self):
        result = self.run_check(DEPLOY_HOST="", DEPLOY_KNOWN_HOSTS="", ENVIRONMENT="production")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Secret DEPLOY_HOST is not set in the production environment", result.stdout)
        self.assertIn("Secret DEPLOY_KNOWN_HOSTS is not set in the production environment", result.stdout)
        self.assertNotIn("DEPLOY_USER", result.stdout)

    def test_optional_secrets_may_be_empty(self):
        result = self.run_check(ADMIN_TOKEN="", APP_TOKEN="", DEPLOY_PORT="")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_quote_in_a_secret_is_refused_without_showing_it(self):
        result = self.run_check(ADMIN_TOKEN="ab'cd")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Secret ADMIN_TOKEN in the staging environment contains a quote", result.stdout)
        self.assertNotIn("ab'cd", result.stdout + result.stderr)


FAKE_DOCKER = """\
#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_LOG"
if [ "$1" = login ]; then
  echo "token=$(cat)" >> "$FAKE_LOG"
  exit 0
fi
if [ "$1 $2" = "compose ps" ]; then
  i=0
  while [ "$i" -lt "${FAKE_CONTAINERS:-1}" ]; do echo "container$i"; i=$((i+1)); done
  exit 0
fi
if [ "$1 $2" = "compose logs" ]; then
  echo "backend log line"
  exit 0
fi
if [ "$1 $2" = "compose pull" ] && [ -n "$FAKE_PULL_FAILS" ]; then
  exit 1
fi
exit 0
"""

FAKE_CURL = """\
#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
if [ -n "$FAKE_HEALTH" ]; then printf '%s' "$FAKE_HEALTH"; exit 0; fi
exit 7
"""


class RemoteDeployScript(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        self.bin = base / "bin"
        self.bin.mkdir()
        self.dir = base / "deploy dir"
        self.dir.mkdir()
        self.log = base / "log"
        for name, body in [("docker", FAKE_DOCKER), ("curl", FAKE_CURL)]:
            path = self.bin / name
            path.write_text(body)
            path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def tearDown(self):
        self.tmp.cleanup()

    def deploy(self, stdin="run-token\n", **env):
        full = {"PATH": f"{self.bin}:{os.environ['PATH']}", "FAKE_LOG": str(self.log),
                "HEALTH_TIMEOUT": "1", "HEALTH_INTERVAL": "0.2"}
        full.update(env)
        result = subprocess.run(["bash", str(SCRIPT), str(self.dir), "octo-actor"],
                                input=stdin, capture_output=True, text=True, env=full,
                                timeout=30)
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        return result, calls

    def test_healthy_deploy(self):
        result, calls = self.deploy(FAKE_HEALTH='{"status": "ok"}')
        self.assertEqual(result.returncode, 0, result.stderr)
        docker = [c for c in calls if c.startswith("docker")]
        self.assertEqual(docker, [
            "docker login ghcr.io -u octo-actor --password-stdin",
            "docker compose pull backend",
            "docker compose up -d --remove-orphans backend",
            "docker compose ps -q backend",
            "docker logout ghcr.io",
        ])
        self.assertIn("token=run-token", calls)
        self.assertTrue(any("http://127.0.0.1:8000/healthz" in c for c in calls))

    def test_token_never_on_a_command_line(self):
        _, calls = self.deploy(FAKE_HEALTH='{"status":"ok"}')
        for call in calls:
            if not call.startswith("token="):
                self.assertNotIn("run-token", call)

    def test_unhealthy_deploy_fails_with_logs(self):
        result, calls = self.deploy(FAKE_HEALTH='{"status":"starting"}')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not answer healthy", result.stderr)
        self.assertIn("backend log line", result.stderr)
        self.assertIn("docker compose logs --no-color --tail 50 backend", calls)
        self.assertEqual(calls[-1], "docker logout ghcr.io")

    def test_no_answer_is_unhealthy(self):
        result, _ = self.deploy()
        self.assertNotEqual(result.returncode, 0)

    def test_more_than_one_container_fails(self):
        result, calls = self.deploy(FAKE_HEALTH='{"status":"ok"}', FAKE_CONTAINERS="2")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one backend container, found 2", result.stderr)
        self.assertFalse(any(c.startswith("curl") for c in calls))

    def test_failed_pull_stops_before_restart(self):
        result, calls = self.deploy(FAKE_HEALTH='{"status":"ok"}', FAKE_PULL_FAILS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("docker compose up -d --remove-orphans backend", calls)
        self.assertEqual(calls[-1], "docker logout ghcr.io")

    def test_no_token_fails_before_docker(self):
        result, calls = self.deploy(stdin="", FAKE_HEALTH='{"status":"ok"}')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c.startswith("docker") for c in calls))

    def test_never_removes_volumes(self):
        # Redeploy keeps configuration: nothing takes the named volume down.
        text = SCRIPT.read_text()
        self.assertNotIn(" down", text)
        self.assertNotIn("-v ", text.replace("--password-stdin", ""))


if __name__ == "__main__":
    unittest.main()
