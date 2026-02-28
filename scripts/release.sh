#!/usr/bin/env bash
set -euo pipefail

uv run cz bump --yes
uv lock
git add uv.lock
git commit -m "chore: sync uv.lock after version bump"
VERSION=$(uv run cz version)
git push origin HEAD
git push origin "v${VERSION}"
