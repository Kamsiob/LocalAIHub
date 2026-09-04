#!/usr/bin/env bash
# Throwaway subjects for exercising removal. Everything is named lah-test* so it
# is unmistakable, and teardown removes exactly those names and nothing else.
#
# Nothing real of the user's is ever a test target. This file is the reason that
# claim can be checked rather than trusted.
set -uo pipefail

QUADLET="$HOME/.config/containers/systemd"
UNITS="$HOME/.config/systemd/user"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"

case "${1:-}" in
setup)
  mkdir -p "$QUADLET" "$UNITS" "$APPS" "$ICONS" \
           "$HOME/.config/lah-testsvc" "$HOME/.cache/lah-testsvc"

  # A named volume holding known content, so its survival can be proven byte
  # for byte rather than merely observed to still exist.
  podman volume create lah-testdata >/dev/null 2>&1
  podman run --rm -v lah-testdata:/d docker.io/library/alpine:latest \
    sh -c 'echo "precious-user-data-do-not-delete" > /d/canary.txt' >/dev/null 2>&1

  cat > "$QUADLET/lah-testsvc.container" <<'Q'
[Unit]
Description=Local AI Hub removal test subject

[Container]
Image=docker.io/library/alpine:latest
ContainerName=lah-testsvc
Exec=sh -c "while true; do printf 'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok' | nc -l -p 8799; done"
PublishPort=127.0.0.1:8799:8799
Volume=lah-testdata:/data

[Service]
Restart=no

[Install]
WantedBy=default.target
Q

  # A unit whose files exist but which starts nothing, for the "unit present,
  # program absent" case.
  cat > "$UNITS/lah-fake.service" <<'U'
[Unit]
Description=Local AI Hub removal test, does nothing

[Service]
Type=oneshot
ExecStart=/bin/true
RemainAfterExit=yes
U

  cat > "$APPS/lah-testsvc.desktop" <<'D'
[Desktop Entry]
Type=Application
Name=LAH Test Subject
Exec=/bin/true
Icon=lah-testsvc
Terminal=false
Categories=Utility;
D
  printf '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24"/></svg>\n' \
    > "$ICONS/lah-testsvc.svg"
  echo "testbed-config"   > "$HOME/.config/lah-testsvc/settings.conf"
  echo "testbed-cache"    > "$HOME/.cache/lah-testsvc/blob.bin"

  systemctl --user daemon-reload
  systemctl --user start lah-testsvc.service >/dev/null 2>&1
  echo "setup complete"
  ;;

status)
  echo "quadlet   : $([ -f "$QUADLET/lah-testsvc.container" ] && echo present || echo absent)"
  echo "unit(gen) : $(systemctl --user is-active lah-testsvc.service 2>/dev/null)"
  echo "fake unit : $([ -f "$UNITS/lah-fake.service" ] && echo present || echo absent)"
  echo "container : $(podman ps -a --filter name=lah-testsvc --format '{{.Names}} {{.State}}' 2>/dev/null | head -1)"
  echo "volume    : $(podman volume ls --format '{{.Name}}' 2>/dev/null | grep -c '^lah-testdata$') (1 = present)"
  echo "canary    : $(podman run --rm -v lah-testdata:/d docker.io/library/alpine:latest cat /d/canary.txt 2>/dev/null || echo '(unreadable)')"
  echo "desktop   : $([ -f "$APPS/lah-testsvc.desktop" ] && echo present || echo absent)"
  echo "icon      : $([ -f "$ICONS/lah-testsvc.svg" ] && echo present || echo absent)"
  echo "config    : $([ -d "$HOME/.config/lah-testsvc" ] && echo present || echo absent)"
  echo "cache     : $([ -d "$HOME/.cache/lah-testsvc" ] && echo present || echo absent)"
  ;;

teardown)
  systemctl --user stop lah-testsvc.service >/dev/null 2>&1
  rm -f "$QUADLET/lah-testsvc.container" "$UNITS/lah-fake.service" \
        "$APPS/lah-testsvc.desktop" "$ICONS/lah-testsvc.svg"
  rm -rf "$HOME/.config/lah-testsvc" "$HOME/.cache/lah-testsvc"
  systemctl --user daemon-reload
  podman rm -f lah-testsvc >/dev/null 2>&1
  podman volume rm -f lah-testdata >/dev/null 2>&1
  echo "teardown complete"
  ;;

*) echo "usage: testbed.sh {setup|status|teardown}"; exit 2;;
esac
