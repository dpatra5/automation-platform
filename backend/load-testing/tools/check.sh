#!/usr/bin/env bash
# Run the same quality gates as CI: lint, format check, type check, tests with coverage.
set -euo pipefail
cd "$(dirname "$0")/.."
ruff check src tests tools
black --check src tests tools
mypy
pytest -q --cov=lt --cov-report=term "$@"
