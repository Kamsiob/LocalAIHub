"""HTTPS that still works when the app is running on a different distro than it
was built on.

The AppImage and standalone builds bundle their own OpenSSL, compiled on Ubuntu,
which has Ubuntu's certificate directory (/usr/lib/ssl/certs) baked in as its
default. That path does not exist on Fedora, Bazzite, Arch, openSUSE or anything
else, and no CA bundle ships inside the build — so on any non-Debian host the
trust store comes up empty and *every* HTTPS request fails certificate
verification. It looks exactly like being offline, which is how it was first
reported: "couldn't reach github.com" on a machine with a working connection.

This module builds the SSL context once, notices when the bundled OpenSSL found
no certificates at all, and falls back to the host's real trust store. Running
from source on a normal system it changes nothing — the default context already
has certificates and is used as-is.
"""
from __future__ import annotations

import os
import ssl
import urllib.request

# Where the major distributions actually keep the CA bundle. Order matters only
# in that the first hit wins; any of them is a complete trust store.
_CA_FILES = (
    "/etc/ssl/certs/ca-certificates.crt",   # Debian, Ubuntu, Arch, Alpine
    "/etc/pki/tls/certs/ca-bundle.crt",     # Fedora, RHEL, Bazzite
    "/etc/ssl/ca-bundle.pem",               # openSUSE
    "/etc/ssl/cert.pem",                    # BSD-ish layouts, some atomic distros
)
_CA_DIRS = (
    "/etc/ssl/certs",
    "/etc/pki/tls/certs",
)

_context: ssl.SSLContext | None = None
_source: str = ""


def _loaded_count(ctx: ssl.SSLContext) -> int:
    try:
        return ctx.cert_store_stats().get("x509", 0)
    except Exception:
        return 0


def _build_context() -> tuple[ssl.SSLContext, str]:
    """Build the context and report where its certificates came from.

    One trap worth naming: `cert_store_stats()` counts only certificates that
    have actually been read into memory. A *directory* store (capath) is looked
    up lazily by hash at verification time, so a perfectly good capath-only
    system reports zero. Counting is therefore used to confirm a cafile loaded,
    and never to conclude that a capath failed.
    """
    ctx = ssl.create_default_context()
    # create_default_context has already tried OpenSSL's compiled-in paths and
    # the SSL_CERT_FILE / SSL_CERT_DIR environment variables.
    if _loaded_count(ctx) > 0:
        return ctx, "system default"

    # Either the defaults are a lazy capath, or this is a bundled OpenSSL
    # pointed at the build distro's directory. Adding the host's own store is
    # correct and harmless in both cases.
    for path in _CA_FILES:
        if os.path.isfile(path):
            try:
                ctx.load_verify_locations(cafile=path)
            except Exception:
                continue
            if _loaded_count(ctx) > 0:
                return ctx, path

    # certifi is not a dependency, but if a build happens to carry it, use it.
    try:
        import certifi  # noqa: PLC0415 - optional, absent in normal runs

        ctx.load_verify_locations(cafile=certifi.where())
        if _loaded_count(ctx) > 0:
            return ctx, "certifi"
    except Exception:
        pass

    # No readable bundle. A directory store may still work, so attach any that
    # exist and describe it as unverifiable rather than as absent.
    for path in _CA_DIRS:
        if os.path.isdir(path):
            try:
                ctx.load_verify_locations(capath=path)
                return ctx, f"{path} (directory)"
            except Exception:
                continue

    # Deliberately NOT falling back to an unverified context. A silent downgrade
    # to "encrypted but unauthenticated" is worse than a clear failure for an app
    # whose whole pitch is that it doesn't do anything behind your back.
    return ctx, ""


def ssl_context() -> ssl.SSLContext:
    global _context, _source
    if _context is None:
        _context, _source = _build_context()
    return _context


def trust_store() -> str:
    """Where the CAs came from, or "" if none were found. For diagnostics."""
    ssl_context()
    return _source


def urlopen(url, timeout: float = 15.0, **kwargs):
    """urllib.request.urlopen with a trust store that survives relocation."""
    return urllib.request.urlopen(url, timeout=timeout, context=ssl_context(), **kwargs)
