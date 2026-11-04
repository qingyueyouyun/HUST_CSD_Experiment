#!/usr/bin/env bash
# Convenience wrapper for the cache/background-load probe.
exec python3 "$(cd "$(dirname "$0")" && pwd)/measure_cache_and_load.py" "$@"
