"""Tests for .github/workflows/backend-deploy.yml (epic #37, task #40).

Docker cannot run in the factory, so these tests prove what can be proved
without it (design.md D15):

* the trigger filters, evaluated the way GitHub evaluates them, for each
  push the spec names;
* the workflow's own shell steps, executed with bash under the inputs that
  matter (branch, missing Dockerfile, owner casing);
* the job and step structure that makes a failed build stop the run before
  anything could contact a server.

Run: python3 .github/workflow-tests/test_backend_deploy.py
Needs Python 3 and PyYAML.
"""

import os
import re
import subprocess
import tempfile
import unittest

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "backend-deploy.yml")


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


def step(wf, name):
    for s in wf["jobs"]["build"]["steps"]:
        if s.get("name") == name:
            return s
    raise AssertionError("no step named %r" % name)


def run_step(script, env, cwd):
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        ["bash", "-e", "-c", script],
        env=full_env,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


class Triggers(unittest.TestCase):
    """Scenarios: Other branches and pull requests; Documents-only push."""

    def setUp(self):
        self.wf = load_workflow()

    def test_only_push_and_manual_start(self):
        self.assertEqual(set(self.wf["on"]), {"push", "workflow_dispatch"})

    def test_no_pull_request_trigger(self):
        for event in ("pull_request", "pull_request_target"):
            self.assertNotIn(event, self.wf["on"])

    def test_other_branch_push_does_not_run(self):
        for branch in ("feature/x", "factory/epic-37", "develop", "staging-old"):
            self.assertFalse(
                push_triggers(self.wf, branch, ["backend/app/main.py"]), branch
            )

    def test_documents_only_push_to_staging_does_not_run(self):
        for files in (
            ["openspec/changes/37-backend-deployment/design.md"],
            ["android/app/src/main/java/Main.kt"],
            ["README.md"],
            [".github/factory-testing.json", ".factory/profile.json"],
            [".claude/settings.json", ".github/workflows/factory-pipeline.yml"],
            [".github/workflow-tests/test_backend_deploy.py"],
        ):
            self.assertFalse(push_triggers(self.wf, "staging", files), files)

    def test_backend_or_deploy_change_runs_on_staging_and_main(self):
        for branch in ("staging", "main"):
            for files in (
                ["backend/app/main.py"],
                ["backend/Dockerfile"],
                ["deploy/compose.yaml"],
                [".github/workflows/backend-deploy.yml"],
                ["openspec/x.md", "backend/requirements.txt"],
            ):
                self.assertTrue(push_triggers(self.wf, branch, files), (branch, files))


class ManualRun(unittest.TestCase):
    """Scenario: Manual run (the trigger and its branch guard)."""

    def setUp(self):
        self.wf = load_workflow()
        self.guard = step(self.wf, "Only staging or main")

    def test_manual_start_has_no_inputs(self):
        self.assertIn("workflow_dispatch", self.wf["on"])
        self.assertFalse((self.wf["on"]["workflow_dispatch"] or {}).get("inputs"))

    def test_guard_is_the_first_step(self):
        self.assertEqual(self.wf["jobs"]["build"]["steps"][0]["name"], "Only staging or main")

    def test_guard_passes_staging_and_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            for branch in ("staging", "main"):
                r = run_step(self.guard["run"], {"BRANCH": branch}, tmp)
                self.assertEqual(r.returncode, 0, (branch, r.stdout, r.stderr))

    def test_guard_fails_any_other_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            for branch in ("feature/x", "factory/epic-37", "Staging", ""):
                r = run_step(self.guard["run"], {"BRANCH": branch}, tmp)
                self.assertNotEqual(r.returncode, 0, branch)
                self.assertIn("::error::Manual deploys run only from staging or main", r.stdout)

    def test_guard_reads_the_branch_from_ref_name(self):
        self.assertEqual(self.guard["env"]["BRANCH"], "${{ github.ref_name }}")


class ImagePublished(unittest.TestCase):
    """Scenario: Image published before deploy."""

    def setUp(self):
        self.wf = load_workflow()
        self.steps = self.wf["jobs"]["build"]["steps"]

    def test_step_order(self):
        order = [s.get("name") for s in self.steps]
        self.assertEqual(
            order,
            [
                "Only staging or main",
                "Check out",
                "Backend present",
                "Image name",
                "Set up Docker Buildx",
                "Log in to GitHub Container Registry",
                "Build and publish",
            ],
        )

    def test_backend_present_fails_without_dockerfile(self):
        s = step(self.wf, "Backend present")
        with tempfile.TemporaryDirectory() as tmp:
            r = run_step(s["run"], {"BRANCH": "staging"}, tmp)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn(
                "::error::backend/Dockerfile is not on staging; the mirror v1 backend must reach this branch first",
                r.stdout,
            )

    def test_backend_present_passes_with_dockerfile(self):
        s = step(self.wf, "Backend present")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "backend"))
            open(os.path.join(tmp, "backend", "Dockerfile"), "w").close()
            r = run_step(s["run"], {"BRANCH": "main"}, tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_image_name_is_lowercase_owner_and_full_commit(self):
        s = step(self.wf, "Image name")
        sha = "0123456789abcdef0123456789abcdef01234567"
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            r = run_step(s["run"], {"OWNER": "GenAI-Jerry", "SHA": sha, "GITHUB_OUTPUT": out}, tmp)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out) as fh:
                self.assertEqual(fh.read().strip(), "image=ghcr.io/genai-jerry/mirror-backend:" + sha)
        self.assertEqual(s["env"]["SHA"], "${{ github.sha }}")

    def test_build_and_publish_uses_backend_context_and_commit_tag(self):
        w = step(self.wf, "Build and publish")["with"]
        self.assertTrue(step(self.wf, "Build and publish")["uses"].startswith("docker/build-push-action@"))
        self.assertEqual(w["context"], "backend")
        self.assertEqual(w["file"], "backend/Dockerfile")
        self.assertIs(w["push"], True)
        self.assertEqual(w["tags"], "${{ steps.image.outputs.image }}")
        self.assertNotIn("latest", str(w["tags"]))
        self.assertNotIn("build-args", w)

    def test_registry_is_ghcr_with_package_write(self):
        login = step(self.wf, "Log in to GitHub Container Registry")["with"]
        self.assertEqual(login["registry"], "ghcr.io")
        self.assertEqual(self.wf["permissions"], {"contents": "read"})
        self.assertEqual(self.wf["jobs"]["build"]["permissions"]["packages"], "write")

    def test_job_exposes_image_for_deploy(self):
        self.assertEqual(
            self.wf["jobs"]["build"]["outputs"]["image"], "${{ steps.image.outputs.image }}"
        )


class BuildFails(unittest.TestCase):
    """Scenario: Build fails — the run fails and no server is contacted."""

    def setUp(self):
        self.wf = load_workflow()

    def test_no_build_step_swallows_a_failure(self):
        job = self.wf["jobs"]["build"]
        self.assertNotIn("continue-on-error", job)
        for s in job["steps"]:
            self.assertNotIn("continue-on-error", s, s.get("name"))
            self.assertNotIn("if", s, s.get("name"))

    def test_build_job_contacts_no_server(self):
        text = yaml.safe_dump(self.wf["jobs"]["build"]).lower()
        for word in ("ssh", "scp", "rsync", "appleboy", "curl", "healthz"):
            self.assertNotIn(word, text)

    def test_every_other_job_waits_for_a_successful_build(self):
        for name, job in self.wf["jobs"].items():
            if name == "build":
                continue
            needs = job.get("needs")
            needs = [needs] if isinstance(needs, str) else (needs or [])
            self.assertIn("build", needs, name)
            cond = str(job.get("if", ""))
            self.assertNotRegex(cond, r"always\(\)|failure\(\)|cancelled\(\)", name)

    def test_every_shell_step_parses(self):
        for s in self.wf["jobs"]["build"]["steps"]:
            if "run" in s:
                r = subprocess.run(["bash", "-n", "-c", s["run"]], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, (s.get("name"), r.stderr))


if __name__ == "__main__":
    unittest.main(verbosity=2)
