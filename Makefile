# test / build / lint for both halves of the product (design decision D1).
#
# The combined targets call scripts/gate.sh, which is also what `commands` in
# .factory/profile.json runs — so "both halves" is defined in one place. The
# app half needs a JDK and an Android SDK; without one the gate runs the
# backend half and says the app half was skipped.
#
# The factory's own runners call scripts/gate.sh directly, because `make` is
# not installed there.

.PHONY: all test build lint install \
        backend-test backend-build backend-lint backend-install \
        app-test app-build app-lint

all: lint test build

test:
	scripts/gate.sh test

build:
	scripts/gate.sh build

lint:
	scripts/gate.sh lint

install: backend-install

backend-install:
	cd backend && uv sync

backend-test: backend-install
	cd backend && uv run pytest

backend-build:
	cd backend && uv build

backend-lint: backend-install
	cd backend && uv run ruff check . && uv run ruff format --check .

app-test:
	cd app && ./gradlew testDevDebugUnitTest

app-build:
	cd app && ./gradlew assembleDebug

app-lint:
	cd app && ./gradlew lint
