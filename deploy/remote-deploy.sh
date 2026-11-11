#!/usr/bin/env bash
# Runs on the server, started by the `deploy` job in
# .github/workflows/backend-deploy.yml (openspec/changes/37-backend-deployment,
# design Task 3, D6, D10, D12).
#
# Usage: bash remote-deploy.sh <deploy-dir> <registry-user>
#   The registry token arrives on standard input (one line) and is never put on
#   a command line. <deploy-dir> holds compose.yaml and the .env the deploy job
#   wrote; Docker Compose reads both from there.
#
# Never add `set -x`: the .env holds the backend's secrets.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: remote-deploy.sh <deploy-dir> <registry-user>" >&2
  exit 2
fi

DEPLOY_DIR="$1"
REGISTRY_USER="$2"
REGISTRY="ghcr.io"
HEALTH_URL="http://127.0.0.1:8000/healthz"
# D12: poll every 3 seconds for up to 90. Overridable only so the tests can run
# in seconds; the deploy job never sets them.
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-90}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-3}"

cd "$DEPLOY_DIR"

# D6: log in with the run's short-lived token, and log out whatever happens.
token=""
IFS= read -r token || true
if [ -z "$token" ]; then
  echo "No registry token on standard input" >&2
  exit 1
fi
trap 'docker logout "$REGISTRY" >/dev/null 2>&1 || true' EXIT
printf '%s\n' "$token" | docker login "$REGISTRY" -u "$REGISTRY_USER" --password-stdin >/dev/null
unset token

# From here on nothing reads standard input.
exec </dev/null

echo "Pulling the backend image"
docker compose pull backend

echo "Starting the backend"
docker compose up -d --remove-orphans backend

running="$(docker compose ps -q backend | grep -c . || true)"
if [ "$running" != "1" ]; then
  echo "Expected exactly one backend container, found ${running}" >&2
  exit 1
fi

echo "Waiting for ${HEALTH_URL} (up to ${HEALTH_TIMEOUT}s)"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
while :; do
  body="$(curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null || true)"
  # Healthy only when the answer is {"status": "ok"} (spaces allowed).
  if printf '%s' "$body" | tr -d '[:space:]' | grep -q '"status":"ok"'; then
    echo "Backend is healthy"
    exit 0
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    break
  fi
  sleep "$HEALTH_INTERVAL"
done

echo "Backend did not answer healthy within ${HEALTH_TIMEOUT}s; last log lines:" >&2
docker compose logs --no-color --tail 50 backend >&2 || true
exit 1
