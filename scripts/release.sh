#!/usr/bin/env bash
set -euo pipefail

uv run cz bump
VERSION=$(uv run cz version)
git push origin HEAD
git push origin "v${VERSION}"
