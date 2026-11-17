#!/usr/bin/env bash
# The nightly's tools: pubfleet's release TAG, and the pubrules that release is
# tested with, which governed repositories then move to (`pubrules nightly` moves
# a repository to the pubrules it runs as). Run from the checkout of pubfleet at
# TAG, whose tests/requirements.lock pins that pubrules by hash.
#
#   install.sh vX.Y.Z
#
# PUBRULES_TAG, a pubrules release tag such as v0.33.1, installs that pubrules
# instead, for a fix that must reach the repositories before pubfleet's own
# nightly has moved its lock to it. PUBFLEET is the repository pubfleet's
# wheel comes from (default Sustenaut/pubfleet).
set -euo pipefail

tag=$1
here=$(cd "$(dirname "$0")/../.." && pwd)
pip=(python -m pip install --quiet)

"${pip[@]}" --only-binary ':all:' --require-hashes -r "$here/tests/requirements.lock"
"${pip[@]}" --no-deps \
  "https://github.com/${PUBFLEET:-Sustenaut/pubfleet}/releases/download/$tag/pubfleet-${tag#v}-py3-none-any.whl"
if [ -n "${PUBRULES_TAG:-}" ]; then
  case $PUBRULES_TAG in
    v[0-9]*.[0-9]*.[0-9]*) ;;
    *) echo "install.sh: the pubrules input must be a release tag such as v0.33.1, not $PUBRULES_TAG" >&2; exit 2 ;;
  esac
  "${pip[@]}" --no-deps \
    "https://github.com/Sustenaut/pubrules/releases/download/$PUBRULES_TAG/pubrules-${PUBRULES_TAG#v}-py3-none-any.whl"
  echo "::warning::The pubrules input overrides the pubrules pubfleet $tag is tested with: governed repositories move to pubrules $PUBRULES_TAG."
fi
pubfleet --version
pubrules --version 2>/dev/null || python -c 'import pubrules; print("pubrules", pubrules.__version__)'
