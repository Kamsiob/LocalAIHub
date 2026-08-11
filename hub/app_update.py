"""Check whether a newer (Local) AI Hub has been released. User-triggered only.

The whole point of this module is what it does *not* do. There is no timer, no
check on launch, no cache warm-up, no "while we're online anyway". `check()` is
called from exactly one place — a button press — and if that button is never
pressed, this file never opens a socket for the lifetime of the process. Import
it freely; importing does nothing.

It also never updates anything. Self-updating is what gets an app rejected from
Flathub, and it would be wrong for a package the user's OS is managing. All this
does is compare two version strings and then point at whichever channel actually
installed the app.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

from . import __version__, net

REPO = "kamsiob/LocalAIHub"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
GEARLEVER = "https://flathub.org/apps/it.mijorus.gearlever"

# Shown in the UI next to the button, before it is pressed. The promise has to
# be specific enough to be checkable, or it isn't worth making.
DISCLOSURE = (
    "Nothing is checked until you press this. It then asks github.com once for "
    "the latest release number and compares it with yours. No account, no "
    "telemetry, and the app never updates itself."
)


def install_method() -> str:
    """How this copy was installed, which decides what the user should do next.

    Flatpak and AppImage both set an unmistakable variable in the environment;
    anything else is a source or standalone run where the releases page is the
    honest answer.
    """
    if os.environ.get("FLATPAK_ID"):
        return "flatpak"
    if os.environ.get("APPIMAGE"):
        return "appimage"
    if getattr(sys, "frozen", False):
        return "standalone"
    return "source"


_ADVICE = {
    "flatpak": ("Updates come from wherever you installed it — your app store, "
                "or `flatpak update`. (Local) AI Hub never updates itself."),
    "appimage": ("Download the new AppImage from the releases page. GearLever "
                 "can keep AppImages updated for you if you'd rather not do it "
                 "by hand."),
    "standalone": "Download the new build from the releases page.",
    "source": "Pull the new tag from the repository, or use the releases page.",
}


def _parse(version: str) -> tuple:
    """"v1.2.0" -> (1, 2, 0). Trailing pre-release text sorts before the release.

    Returns () for anything unparseable, which the caller treats as "can't
    compare" rather than guessing a direction.
    """
    text = (version or "").strip().lstrip("vV")
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(.*)$", text)
    if not match:
        return ()
    nums = tuple(int(g or 0) for g in match.groups()[:3])
    suffix = (match.group(4) or "").strip()
    # A pre-release ("1.2.0-rc1") is older than the release it precedes.
    return nums + ((0, suffix) if suffix.startswith("-") else (1, ""))


def check(timeout: float = 12.0) -> dict:
    """Ask GitHub for the latest release tag and compare. Called on press only.

    Always returns a dict with a `state` of "newer", "current" or "error" — the
    three calm outcomes the UI knows how to show. Nothing raises out of here, so
    the UI never has to render a traceback or spin forever.
    """
    method = install_method()
    result = {
        "state": "error",
        "current": __version__,
        "latest": "",
        "method": method,
        "advice": _ADVICE.get(method, _ADVICE["source"]),
        "releases_url": RELEASES_PAGE,
        "gearlever_url": GEARLEVER if method == "appimage" else "",
        "detail": "",
    }

    req = urllib.request.Request(
        LATEST_API,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": f"LocalAIHub/{__version__}"},
    )
    try:
        with net.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        result["detail"] = (
            "GitHub hasn't published a release yet." if exc.code == 404
            else f"GitHub replied {exc.code}.")
        return result
    except ssl.SSLError as exc:
        # Reported separately because it is emphatically not a network problem,
        # and saying "couldn't reach github.com" on a machine with a working
        # connection sends people to debug the wrong thing entirely.
        result["detail"] = (
            "The secure connection couldn't be verified"
            f"{' (no CA certificates found on this system)' if not net.trust_store() else ''}."
        )
        result["error_kind"] = "tls"
        return result
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ssl.SSLError):
            result["detail"] = (
                "The secure connection couldn't be verified"
                f"{' (no CA certificates found on this system)' if not net.trust_store() else ''}."
            )
            result["error_kind"] = "tls"
        else:
            result["detail"] = "Couldn't reach github.com."
            result["error_kind"] = "network"
        return result
    except Exception:
        result["detail"] = "Couldn't reach github.com."
        result["error_kind"] = "network"
        return result

    latest = (data.get("tag_name") or data.get("name") or "").strip()
    result["latest"] = latest.lstrip("vV")
    result["release_url"] = data.get("html_url") or RELEASES_PAGE

    here, there = _parse(__version__), _parse(latest)
    if not here or not there:
        result["detail"] = "Couldn't read the version numbers to compare them."
        return result

    result["state"] = "newer" if there > here else "current"
    return result
