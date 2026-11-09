#!/usr/bin/env bash
#
# Run one gate — test, build or lint — over both halves of the product
# (design decision D1: backend/ and app/ ship together).
#
# This is what `commands` in .factory/profile.json runs, and what the
# Makefile's combined targets call, so "both halves" is defined once.
#
# The backend half always runs. The app half needs a JDK and an Android SDK
# on the machine; where there is none the gate says so, loudly, and runs the
# backend half alone. Set MIRROR_APP_GATE=required to turn that notice into a
# failure — do that on a machine that is supposed to have the Android SDK.
#
# Usage: scripts/gate.sh <test|build|lint>

set -euo pipefail

GATE="${1:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$GATE" in
    test | build | lint) ;;
    *)
        echo "usage: scripts/gate.sh <test|build|lint>" >&2
        exit 2
        ;;
esac

run_backend() {
    cd "$ROOT/backend"
    case "$GATE" in
        test) uv run pytest ;;
        build) uv build ;;
        lint) uv run ruff check . && uv run ruff format --check . ;;
    esac
}

# An Android SDK is here when the SDK is where one of the usual pointers says
# it is.
android_sdk_dir() {
    local candidate
    for candidate in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" "$HOME/Android/Sdk"; do
        if [ -n "$candidate" ] && [ -d "$candidate/platforms" ]; then
            echo "$candidate"
            return 0
        fi
    done
    if [ -f "$ROOT/app/local.properties" ]; then
        candidate="$(sed -n 's/^sdk\.dir=//p' "$ROOT/app/local.properties" | head -1)"
        if [ -n "$candidate" ] && [ -d "$candidate/platforms" ]; then
            echo "$candidate"
            return 0
        fi
    fi
    return 1
}

run_app() {
    cd "$ROOT/app"
    case "$GATE" in
        # dev is the flavour a developer builds; systemTest differs only in
        # which backend it points at, so one flavour proves the unit tests.
        test) ./gradlew --quiet testDevDebugUnitTest ;;
        build) ./gradlew --quiet assembleDebug ;;
        lint) ./gradlew --quiet lint ;;
    esac
}

echo "== backend: $GATE"
run_backend

echo
if ! command -v java >/dev/null 2>&1 || ! android_sdk_dir >/dev/null; then
    message="== app: $GATE SKIPPED — no JDK or Android SDK on this machine (see README)"
    if [ "${MIRROR_APP_GATE:-}" = "required" ]; then
        echo "$message" >&2
        echo "   MIRROR_APP_GATE=required, so this is a failure." >&2
        exit 1
    fi
    echo "$message"
    exit 0
fi

echo "== app: $GATE"
run_app
