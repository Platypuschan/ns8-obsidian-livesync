#!/bin/bash
set -Eeuo pipefail
case "${1:-}" in
  build) exec ./build-ui.sh ;;
  watch) yarn install --immutable; exec yarn watch ;;
  serve) yarn install --immutable; shift; exec yarn serve --host 0.0.0.0 --port 8080 "$@" ;;
  *) echo "Append build, watch or serve" >&2; exit 2 ;;
esac
