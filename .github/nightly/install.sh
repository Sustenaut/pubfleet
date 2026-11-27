#!/usr/bin/env bash
# The nightly's tools: pubfleet's release TAG, and the pubrules governed
# repositories then move to (`pubrules nightly` moves a repository to the
# pubrules it runs as). Run from the checkout of pubfleet at TAG.
#
#   install.sh vX.Y.Z
#
# It installs TAG's tests/requirements.lock, by hash, then pubrules' latest
# release, checked against the sha256 GitHub gives for its wheel, and keeps it
# only when `pubfleet pubrules-api --check` says its api has the names and
# shapes pubfleet was tested on. Otherwise it goes back to the pubrules the
# lock pins, with a warning. So a pubrules release reaches governed
# repositories the next night, with no pubfleet release in between, unless it
# changed what pubfleet imports.
#
# PUBRULES_TAG, a pubrules release tag such as v0.33.1, installs that pubrules
# instead, unchecked, for a fix that cannot wait. PUBFLEET is the repository
# pubfleet's wheel comes from (default Sustenaut/pubfleet); PUBRULES_REPO the
# one pubrules' releases come from (default Sustenaut/pubrules).
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
else
  repo=${PUBRULES_REPO:-Sustenaut/pubrules}
  latest=$(gh release view --repo "$repo" --json tagName --jq .tagName || true)
  wheel="pubrules-${latest#v}-py3-none-any.whl"
  digest=$(gh release view "$latest" --repo "$repo" --json assets \
    --jq ".assets[] | select(.name == \"$wheel\") | .digest" | sed 's/^sha256://' || true)
  dir=$(mktemp -d)
  if [ -z "$latest" ] || [ -z "$digest" ] || ! gh release download "$latest" --repo "$repo" --pattern "$wheel" --dir "$dir" \
      || [ "$(sha256sum "$dir/$wheel" | cut -d' ' -f1)" != "$digest" ]; then
    echo "::warning::pubrules $latest's wheel could not be read and checked against its sha256: staying on the pubrules pubfleet $tag is tested with."
  else
    "${pip[@]}" --no-deps "$dir/$wheel"
    if ! pubfleet pubrules-api --check; then
      echo "::warning::pubrules $latest changed what pubfleet imports from pubrules.api: staying on the pubrules pubfleet $tag is tested with, until a pubfleet release is."
      "${pip[@]}" --force-reinstall --no-deps --only-binary ':all:' --require-hashes -r "$here/tests/requirements.lock"
    fi
  fi
fi
pubfleet --version
pubrules --version 2>/dev/null || python -c 'import pubrules; print("pubrules", pubrules.__version__)'
