#!/usr/bin/env bash
#
# Run image2sqlitedbmap in a Docker container.
# Usage: ./run.sh <map_file> [options]
#   ./run.sh /path/to/map.map
#   ./run.sh /path/to/map.map -f mbtiles -o output.mbtiles
#   ./run.sh /path/to/map.map -q
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_NAME="image2sqlitedbmap"

# Build image if it doesn't exist
if ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
    echo "Building Docker image '$IMAGE_NAME'..."
    docker build -t "$IMAGE_NAME" -f "$SCRIPT_DIR/Dockerfile" "$PROJECT_DIR"
fi

# Need at least the .map file path
if [ $# -eq 0 ]; then
    echo "Usage: $0 <map_file> [options]"
    echo ""
    echo "Options are passed to the application, see: python main.py --help"
    exit 1
fi

# Resolve to absolute path
MAP_FILE="$(realpath "$1")"
MAP_DIR="$(dirname "$MAP_FILE")"
MAP_NAME="$(basename "$MAP_FILE")"
shift

exec docker run --rm -it \
    -v "$MAP_DIR:/data" \
    -w /data \
    "$IMAGE_NAME" \
    "/data/$MAP_NAME" "$@"
