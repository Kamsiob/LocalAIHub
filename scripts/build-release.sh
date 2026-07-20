#!/usr/bin/env bash
# Build the release artifacts (AppImage + standalone tarball) in an ubuntu:22.04
# container, so the result runs on a low glibc baseline (most current Linux
# desktops) rather than only this build machine.
#
#   scripts/build-release.sh
#
# Output: dist/release/  (gitignored)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="docker.io/library/ubuntu:22.04"

command -v podman >/dev/null || { echo "podman is required"; exit 1; }

mkdir -p "$REPO/dist/release" "$REPO/dist/_build"
echo "==> Building release in $IMAGE (repo: $REPO)"

# Disk-backed build dir (QtWebEngine bundles are multi-GB across intermediate
# copies — too large for a RAM tmpfs).
podman run --rm \
  -v "$REPO":/src:Z \
  -v "$REPO/dist/_build":/work:Z \
  -w /work \
  "$IMAGE" \
  bash /src/packaging/build-in-container.sh

echo "==> Artifacts:"
ls -la "$REPO/dist/release"
