"""Tests for deploy/compose.yaml (openspec/changes/37-backend-deployment, Task 1).

Run from the repository root:
    python3 -m unittest discover -s deploy/tests -v

Needs PyYAML. The `docker compose config` tests run when a Docker Compose v2
binary is found (`docker compose`, or `docker-compose`, or the path in
COMPOSE_BIN); they are skipped otherwise. `docker compose config` needs no
Docker daemon.

Scenarios served (backend-deployment spec):
- Settings reach the container: the wiring from the server's `.env` into the
  backend container's environment.
- Redeploy keeps configuration: the runtime-configuration directory is on a
  named volume, which `docker compose up -d` keeps when it recreates the
  container.
"""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "deploy" / "compose.yaml"
CONFIG_DIR = "/var/lib/mirror/runtime-config"


def _compose_cmd():
    explicit = os.environ.get("COMPOSE_BIN")
    if explicit:
        return [explicit]
    if shutil.which("docker"):
        probe = subprocess.run(
            ["docker", "compose", "version"], capture_output=True, text=True
        )
        if probe.returncode == 0:
            return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return None


COMPOSE = _compose_cmd()


class ComposeFileStructure(unittest.TestCase):
    """What the file says, read as YAML."""

    @classmethod
    def setUpClass(cls):
        cls.doc = yaml.safe_load(COMPOSE_FILE.read_text())
        cls.backend = cls.doc["services"]["backend"]

    def test_project_name_is_fixed(self):
        self.assertEqual(self.doc["name"], "mirror")

    def test_exactly_one_service(self):
        self.assertEqual(list(self.doc["services"]), ["backend"])

    def test_settings_come_from_environment(self):
        env = self.backend["environment"]
        self.assertEqual(
            env["SARVAM_API_KEY"], "${SARVAM_API_KEY:?SARVAM_API_KEY is not set}"
        )
        self.assertEqual(env["ADMIN_TOKEN"], "${ADMIN_TOKEN:-}")
        self.assertEqual(env["APP_TOKEN"], "${APP_TOKEN:-}")

    def test_runtime_config_on_named_volume(self):
        self.assertIn(f"runtime-config:{CONFIG_DIR}", self.backend["volumes"])
        self.assertIn("runtime-config", self.doc["volumes"])

    def test_no_secret_or_address_in_file(self):
        def scalars(node):
            if isinstance(node, dict):
                for v in node.values():
                    yield from scalars(v)
            elif isinstance(node, list):
                for v in node:
                    yield from scalars(v)
            elif node is not None:
                yield str(node)

        allowed = {
            "mirror",
            "unless-stopped",
            "8000:8000",
            f"runtime-config:{CONFIG_DIR}",
        }
        for value in scalars(self.doc):
            if value.startswith("${"):
                continue  # filled from the server's .env
            # Only fixed, non-secret values are allowed.
            self.assertIn(value, allowed, f"unexpected literal value: {value!r}")


@unittest.skipIf(COMPOSE is None, "Docker Compose v2 not available")
class ComposeConfig(unittest.TestCase):
    """What Docker Compose makes of the file and a server `.env`."""

    def _config(self, env_lines):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            shutil.copy(COMPOSE_FILE, tmp / "compose.yaml")
            (tmp / ".env").write_text("\n".join(env_lines) + "\n")
            clean_env = {
                k: v
                for k, v in os.environ.items()
                if k
                not in {"BACKEND_IMAGE", "SARVAM_API_KEY", "ADMIN_TOKEN", "APP_TOKEN"}
            }
            return subprocess.run(
                COMPOSE
                + ["-f", str(tmp / "compose.yaml"), "config", "--format", "json"],
                cwd=tmp,
                capture_output=True,
                text=True,
                env=clean_env,
            )

    def test_settings_reach_the_container(self):
        result = self._config(
            [
                "BACKEND_IMAGE=ghcr.io/example/mirror-backend:abc123",
                "SARVAM_API_KEY=test-sarvam-key",
                "ADMIN_TOKEN=test-admin",
                "APP_TOKEN=test-app",
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        backend = json.loads(result.stdout)["services"]["backend"]
        self.assertEqual(backend["image"], "ghcr.io/example/mirror-backend:abc123")
        self.assertEqual(
            backend["environment"],
            {
                "SARVAM_API_KEY": "test-sarvam-key",
                "ADMIN_TOKEN": "test-admin",
                "APP_TOKEN": "test-app",
            },
        )

    def test_optional_tokens_default_to_empty(self):
        result = self._config(
            [
                "BACKEND_IMAGE=ghcr.io/example/mirror-backend:abc123",
                "SARVAM_API_KEY=test-sarvam-key",
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        env = json.loads(result.stdout)["services"]["backend"]["environment"]
        self.assertEqual(env["ADMIN_TOKEN"], "")
        self.assertEqual(env["APP_TOKEN"], "")

    def test_missing_sarvam_key_is_refused(self):
        result = self._config(["BACKEND_IMAGE=ghcr.io/example/mirror-backend:abc123"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SARVAM_API_KEY is not set", result.stderr)

    def test_missing_image_is_refused(self):
        result = self._config(["SARVAM_API_KEY=test-sarvam-key"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BACKEND_IMAGE is not set", result.stderr)

    def test_runtime_config_volume_survives_recreate(self):
        result = self._config(
            [
                "BACKEND_IMAGE=ghcr.io/example/mirror-backend:abc123",
                "SARVAM_API_KEY=test-sarvam-key",
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        cfg = json.loads(result.stdout)
        mounts = cfg["services"]["backend"]["volumes"]
        self.assertEqual(len(mounts), 1)
        self.assertEqual(mounts[0]["type"], "volume")
        self.assertEqual(mounts[0]["source"], "runtime-config")
        self.assertEqual(mounts[0]["target"], CONFIG_DIR)
        # A named (not anonymous) volume in project "mirror": `up -d` keeps it.
        self.assertEqual(cfg["volumes"]["runtime-config"]["name"], "mirror_runtime-config")


if __name__ == "__main__":
    unittest.main()
