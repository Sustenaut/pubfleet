#!/usr/bin/env bash
# The nightly's tools: pubfleet's release TAG, and the pubkit that release is
# tested with, which governed repositories then move to (`pubkit nightly` moves
# a repository to the pubkit it runs as). Run from the checkout of pubfleet at
# TAG, whose tests/requirements.lock pins that pubkit by hash.
#
#   install.sh vX.Y.Z
#
# PUBKIT_TAG, a pubkit release tag such as v0.33.1, installs that pubkit
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
if [ -n "${PUBKIT_TAG:-}" ]; then
  case $PUBKIT_TAG in
    v[0-9]*.[0-9]*.[0-9]*) ;;
    *) echo "install.sh: the pubkit input must be a release tag such as v0.33.1, not $PUBKIT_TAG" >&2; exit 2 ;;
  esac
  "${pip[@]}" --no-deps \
    "https://github.com/Sustenaut/pubkit/releases/download/$PUBKIT_TAG/pubkit-${PUBKIT_TAG#v}-py3-none-any.whl"
  echo "::warning::The pubkit input overrides the pubkit pubfleet $tag is tested with: governed repositories move to pubkit $PUBKIT_TAG."
fi
pubfleet --version
pubkit --version 2>/dev/null || python -c 'import pubkit; print("pubkit", pubkit.__version__)'
