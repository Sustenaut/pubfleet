#!/usr/bin/env bash
# Whether tonight's pubrules is at least the one a repository already runs: the
# version its managed ./pubrules names. `pubrules nightly` moves a repository to the
# pubrules it runs as, so an older one installed (a pubfleet release whose lock
# lags a pubrules release the repository already took) would move it backwards.
# Exit 0 to go on, 1 with one line saying why not. A repository without a
# managed ./pubrules goes on.
#
#   not-backwards.sh [CHECKOUT]
set -euo pipefail

dir=${1:-.}
pinned=$( { sed -n 's/^# Managed by pubrules \([0-9][0-9.]*[0-9]\):.*/\1/p' "$dir/pubrules" 2>/dev/null || true; } | head -n 1)
[[ -n "$pinned" ]] || exit 0
installed=$(pubrules --version | awk '{print $NF}')
[[ "$installed" == "$pinned" ]] && exit 0
if [[ "$(printf '%s\n%s\n' "$pinned" "$installed" | sort -V | head -n 1)" == "$installed" ]]; then
  echo "it runs pubrules $pinned, newer than tonight's $installed: not moved back"
  exit 1
fi
