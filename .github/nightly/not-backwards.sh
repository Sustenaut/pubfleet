#!/usr/bin/env bash
# Whether tonight's pubkit is at least the one a repository already runs: the
# version its managed ./pubkit names. `pubkit nightly` moves a repository to the
# pubkit it runs as, so an older one installed (a pubfleet release whose lock
# lags a pubkit release the repository already took) would move it backwards.
# Exit 0 to go on, 1 with one line saying why not. A repository without a
# managed ./pubkit goes on.
#
#   not-backwards.sh [CHECKOUT]
set -euo pipefail

dir=${1:-.}
pinned=$( { sed -n 's/^# Managed by pubkit \([0-9][0-9.]*[0-9]\):.*/\1/p' "$dir/pubkit" 2>/dev/null || true; } | head -n 1)
[[ -n "$pinned" ]] || exit 0
installed=$(pubkit --version | awk '{print $NF}')
[[ "$installed" == "$pinned" ]] && exit 0
if [[ "$(printf '%s\n%s\n' "$pinned" "$installed" | sort -V | head -n 1)" == "$installed" ]]; then
  echo "it runs pubkit $pinned, newer than tonight's $installed: not moved back"
  exit 1
fi
