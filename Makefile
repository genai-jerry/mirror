# test / build / lint for both halves of the product (design decision D1).
# The app half is added by the app scaffold task; until then these targets
# cover the backend only.
#
# The factory's own runners call the underlying commands directly, because
# `make` is not installed there — see `commands` in .factory/profile.json.

.PHONY: all test build lint install \
        backend-test backend-build backend-lint backend-install

all: lint test build

test: backend-test
build: backend-build
lint: backend-lint
install: backend-install

backend-install:
	cd backend && uv sync

backend-test: backend-install
	cd backend && uv run pytest

backend-build:
	cd backend && uv build

backend-lint: backend-install
	cd backend && uv run ruff check . && uv run ruff format --check .
