#!/usr/bin/env bash
# Build the two GateANN binaries used by the course experiment.
set -euo pipefail

repo=${1:?usage: build.sh /path/to/GateANN-public}
repo=$(cd "$repo" && pwd)
jobs=${JOBS:-$(nproc)}

cmake -S "$repo" -B "$repo/build" -DCMAKE_BUILD_TYPE=Release -DUSE_AIO=ON
cmake --build "$repo/build" --target search_disk_index_yfcc build_disk_index -j "$jobs"
echo "Built: $repo/build/tests/search_disk_index_yfcc"
