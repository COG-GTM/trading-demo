#!/usr/bin/env bash
# Render architecture.dot to PNG and SVG. Requires Graphviz (`sudo apt-get install -y graphviz fonts-dejavu`).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
dot -Tpng -Gdpi=110 architecture.dot -o architecture.png
dot -Tsvg architecture.dot -o architecture.svg
echo "Rendered architecture.png and architecture.svg"
