#!/usr/bin/env bash
# Apply the hybrid-tunneling patch to a GateANN checkout.
#
# Usage:
#   bash scripts/apply_patch.sh /path/to/GateANN-public
#   AIO_PATCH=/path/to/gateann_aio_compat.patch bash scripts/apply_patch.sh /path/to/GateANN
#
# The AIO patch is optional and is only needed for the course build
# (-DUSE_AIO=ON).  The hybrid patch itself does not touch the AIO code.
set -euo pipefail

repo=${1:?usage: apply_patch.sh /path/to/GateANN-public}
repo=$(cd "$repo" && pwd)
here=$(cd "$(dirname "$0")" && pwd)
patch_file="$here/../patch/0001-hybrid-tunneling.patch"
expected=71e87cbf0e25c0400c0109dd25a64a7c4dccc9dd

if [ ! -d "$repo/.git" ]; then
  echo "ERROR: not a git checkout: $repo" >&2
  exit 2
fi

head=$(git -C "$repo" rev-parse HEAD)
if [ "$head" != "$expected" ]; then
  echo "WARNING: HEAD is $head, expected $expected"
  echo "         The patch was generated against $expected."
fi

if [ -n "${AIO_PATCH:-}" ]; then
  if git -C "$repo" apply --reverse --check "$AIO_PATCH" >/dev/null 2>&1; then
    echo "AIO compatibility patch already applied."
  else
    git -C "$repo" apply "$AIO_PATCH"
    echo "Applied AIO compatibility patch."
  fi
fi

if git -C "$repo" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
  echo "Hybrid patch already applied."
elif git -C "$repo" apply --check "$patch_file"; then
  git -C "$repo" apply "$patch_file"
  echo "Applied hybrid patch."
else
  echo "ERROR: hybrid patch does not apply cleanly." >&2
  exit 2
fi
