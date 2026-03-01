#!/usr/bin/env bash
set -euo pipefail

# Self-healing: if the current version's tag is missing (e.g. a previous
# bump pushed the commit but failed before pushing the tag), recreate it
# at the original bump commit so cz bump can do an incremental diff.
CURRENT_VERSION=$(uv run cz version --project)
TAG="v${CURRENT_VERSION}"
if ! git rev-parse "$TAG" >/dev/null 2>&1; then
  BUMP_SHA=$(git log --all --format="%H" --grep="^bump: version.*→ ${CURRENT_VERSION}$" | head -1)
  if [ -n "$BUMP_SHA" ]; then
    echo "Recovering missing tag $TAG at $BUMP_SHA"
    git tag "$TAG" "$BUMP_SHA"
  else
    echo "ERROR: version ${CURRENT_VERSION} has no tag and no bump commit found" >&2
    exit 1
  fi
fi

# Bump version — creates commit + tag locally
uv run cz bump --yes
VERSION=$(uv run cz version --project)

# Push bump commit and tag together before any optional steps,
# so we never end up with a pushed commit but missing tag.
git push origin HEAD "v${VERSION}"

# Sync lockfile (best-effort — if this fails, the tag is already pushed)
uv lock
if ! git diff --quiet uv.lock; then
  git add uv.lock
  git commit -m "chore: sync uv.lock after version bump"
  git push origin HEAD
fi
