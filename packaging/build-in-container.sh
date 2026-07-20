#!/usr/bin/env bash
# Runs INSIDE ubuntu:22.04 (glibc 2.35 — a low baseline that runs on most current
# Linux desktops). Produces, in /src/dist/release:
#   - local-ai-hub-<ver>-x86_64.AppImage   (single portable file, the friendly download)
#   - local-ai-hub-<ver>-standalone-linux-x86_64.tar.gz  (no-Python folder build)
#
# The repo is mounted read-only-ish at /src; all building happens in /work.
set -euo pipefail

SRC=/src
WORK=/work
STAGE="$WORK/stage"
APPDIR="$WORK/AppDir"
OUT="$SRC/dist/release"
NAME=local-ai-hub
ARCH=x86_64
PYSIDE_VER=6.11.1

VERSION="$(sed -n 's/^__version__ *= *"\([^"]*\)".*/\1/p' "$SRC/hub/__init__.py")"
VERSION="${VERSION:-1.0.0}"
echo "==> Building $NAME $VERSION ($ARCH) on $(. /etc/os-release; echo "$PRETTY_NAME"), glibc $(ldd --version | head -1 | grep -o '[0-9]\+\.[0-9]\+$')"

# ---- 1. toolchain + libs to bundle -----------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# python + build helpers; NSS/NSPR provide the .so files QtWebEngine dlopens at
# runtime and that minimal target systems often lack — we bundle them.
apt-get install -y -qq --no-install-recommends \
  python3 python3-venv python3-pip libpython3.10 \
  binutils file wget ca-certificates zsync \
  libnss3 libnspr4 >/dev/null
echo "==> apt deps installed"

# ---- 2. python env + freeze -------------------------------------------------
python3 -m venv "$WORK/venv"
. "$WORK/venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet "pyside6==${PYSIDE_VER}" pyinstaller
echo "==> pyinstaller $(pyinstaller --version), $(python -c 'import PySide6; print("PySide6", PySide6.__version__)')"

cd "$WORK"
cp -a "$SRC/app.py" "$SRC/hub" "$SRC/web" "$WORK/"

pyinstaller --noconfirm --clean --name "$NAME" --onedir --windowed \
  --add-data "web:web" \
  --hidden-import PySide6.QtWebEngineWidgets \
  --hidden-import PySide6.QtWebEngineCore \
  --hidden-import PySide6.QtWebChannel \
  --hidden-import PySide6.QtNetwork \
  --exclude-module PySide6.QtQuick3D \
  --exclude-module PySide6.Qt3DCore \
  --exclude-module tkinter \
  "$WORK/app.py"
echo "==> pyinstaller onedir built"

# PyInstaller under-collects the Qt runtime for this PySide6 wheel (it bundles the
# Qt .so libraries but not the platform plugins, QtWebEngineProcess, resources,
# locales or translations). Overlay the complete Qt tree straight from the wheel so
# nothing is missing, and drop a qt.conf so Qt resolves plugins + WebEngine data
# from the bundled prefix.
SITE="$WORK/venv/lib/python3.10/site-packages"
echo "==> overlaying full PySide6 Qt runtime (plugins/resources/translations/libexec)"
cp -a "$SITE/PySide6/Qt/." "dist/$NAME/_internal/PySide6/Qt/"
printf '[Paths]\nPrefix = _internal/PySide6/Qt\n' > "dist/$NAME/qt.conf"
echo "==> Qt tree now has: $(find "dist/$NAME/_internal/PySide6/Qt/plugins/platforms" -name 'libq*.so' 2>/dev/null | wc -l) platform plugins, QtWebEngineProcess=$( [ -e "dist/$NAME/_internal/PySide6/Qt/libexec/QtWebEngineProcess" ] && echo yes || echo NO )"

# Drop the bundled libstdc++/libgcc. They are older than a modern host's, and the
# host's GPU drivers (loaded into our process for GL) link against whichever
# libstdc++ is on LD_LIBRARY_PATH — an older bundled one lacks the newer GLIBCXX
# the host driver needs, breaking rendering. The host copy (>= our ubuntu 22.04
# build baseline) serves both the app and its drivers.
find "dist/$NAME/_internal" \( -name 'libstdc++.so*' -o -name 'libgcc_s.so*' \) -delete
echo "==> removed bundled libstdc++/libgcc (host copy is used instead)"

# ---- 3. common staging dir (shared by tarball + AppImage) ------------------
rm -rf "$STAGE"; mkdir -p "$STAGE/lib"
cp -a "dist/$NAME/." "$STAGE/"

# Bundle NSS/NSPR so WebEngine's network/cert stack loads on systems without it.
for lib in libnss3 libnssutil3 libsmime3 libssl3 libnspr4 libplc4 libplds4 \
           libsoftokn3 libfreebl3 libnssckbi libnssdbm3; do
  for f in /usr/lib/x86_64-linux-gnu/${lib}.so /usr/lib/x86_64-linux-gnu/nss/${lib}.so; do
    [ -e "$f" ] && cp -a "$f" "$STAGE/lib/" || true
  done
done
echo "==> bundled $(ls "$STAGE/lib" | wc -l) NSS/NSPR libs"

# a plain launcher for the folder build (sets lib path, then runs the exe)
cat > "$STAGE/run.sh" <<'RUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
QTROOT="$HERE/_internal/PySide6/Qt"
export LD_LIBRARY_PATH="$HERE/lib:$QTROOT/lib:$HERE/_internal:$LD_LIBRARY_PATH"
export QT_PLUGIN_PATH="$QTROOT/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="$QTROOT/plugins/platforms"
export QTWEBENGINEPROCESS_PATH="$QTROOT/libexec/QtWebEngineProcess"
export QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --no-sandbox ${QTWEBENGINE_CHROMIUM_FLAGS:-}"
exec "$HERE/local-ai-hub" "$@"
RUN
chmod +x "$STAGE/run.sh"

cat > "$STAGE/README.txt" <<EOF
Local AI Hub $VERSION — standalone Linux build (no Python needed)

Run it:
    ./run.sh

Requires a Linux desktop with a graphical session. It manages your local
systemd --user services (Ollama, Open WebUI, ComfyUI); services that aren't
installed simply show as "Not installed".

Homepage: https://kamsiob.com   Source: https://github.com/kamsiob/local-ai-hub
EOF

# ---- 4. standalone tarball --------------------------------------------------
mkdir -p "$OUT"
TARROOT="$NAME-$VERSION"
rm -rf "$WORK/$TARROOT"; cp -a "$STAGE" "$WORK/$TARROOT"
tar -C "$WORK" -czf "$OUT/$NAME-$VERSION-standalone-linux-$ARCH.tar.gz" "$TARROOT"
echo "==> standalone tarball: $(du -h "$OUT/$NAME-$VERSION-standalone-linux-$ARCH.tar.gz" | cut -f1)"

# ---- 6. AppDir --------------------------------------------------------------
# Icon is pre-rendered on the host (packaging/local-ai-hub-256.png) so the build
# container needs no Qt/X system libs just to rasterize an SVG.
ICON="$SRC/packaging/$NAME-256.png"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$STAGE/local-ai-hub" "$STAGE/_internal" "$STAGE/qt.conf" "$APPDIR/usr/bin/"
cp -a "$STAGE/lib/." "$APPDIR/usr/lib/"
cp "$SRC/packaging/AppRun" "$APPDIR/AppRun"; chmod +x "$APPDIR/AppRun"
cp "$SRC/packaging/$NAME.desktop" "$APPDIR/$NAME.desktop"
cp "$SRC/packaging/$NAME.desktop" "$APPDIR/usr/share/applications/$NAME.desktop"
cp "$ICON" "$APPDIR/$NAME.png"
cp "$ICON" "$APPDIR/usr/share/icons/hicolor/256x256/apps/$NAME.png"

# ---- 7. appimagetool --------------------------------------------------------
wget -q -O "$WORK/appimagetool" \
  "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
chmod +x "$WORK/appimagetool"
export ARCH
# no FUSE in the container -> run the tool extracted; skip appstream embedding here
"$WORK/appimagetool" --appimage-extract-and-run --no-appstream \
  "$APPDIR" "$OUT/$NAME-$VERSION-$ARCH.AppImage"
chmod +x "$OUT/$NAME-$VERSION-$ARCH.AppImage"
echo "==> AppImage: $(du -h "$OUT/$NAME-$VERSION-$ARCH.AppImage" | cut -f1)"

echo "==> DONE. Artifacts in $OUT:"
ls -la "$OUT"
