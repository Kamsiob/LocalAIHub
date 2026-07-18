"""ComfyUI model provenance + updates (Hugging Face, Civitai, direct URL).

ComfyUI model files carry no source or version, so — unlike Ollama, which has a
registry — we can only offer "Update" if we know where each file came from. This
module keeps a small local **provenance manifest** mapping each model file to its
source, then checks that source for a newer version and (on request) downloads
and atomically replaces the file.

Privacy: update-checks and downloads only ever contact the model's own host
(huggingface.co / civitai.com / a URL you gave), and only when explicitly
invoked from the UI. Nothing runs in the background; nothing else is contacted.

Manifest: ~/.config/local-ai-hub/comfy_models.json  (local JSON, no telemetry)
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .. import config

MANIFEST_FILE = config.CONFIG_DIR / "comfy_models.json"
USER_AGENT = "local-ai-hub/1.0 (+https://github.com/Kamsiob/local-ai-hub)"

CIVITAI_BY_HASH = "https://civitai.com/api/v1/model-versions/by-hash/{sha}"
CIVITAI_MODEL = "https://civitai.com/api/v1/models/{id}"
HF_RESOLVE = "https://huggingface.co/{repo}/resolve/{rev}/{path}"
HF_TREE = "https://huggingface.co/api/models/{repo}/tree/{rev}?recursive=true"


# --------------------------------------------------------------------------- #
# low-level helpers
# --------------------------------------------------------------------------- #
def _key(path) -> str:
    return str(Path(path).resolve())


def sha256_file(path, progress_cb: Optional[Callable[[float], None]] = None) -> str:
    """SHA256 of a file, streamed (models are large). progress_cb(fraction)."""
    p = Path(path)
    total = p.stat().st_size or 1
    done = 0
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while True:
            chunk = fh.read(8 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            done += len(chunk)
            if progress_cb:
                progress_cb(done / total)
    return h.hexdigest()


def _request(url: str, method: str = "GET", headers: Optional[dict] = None,
             follow: bool = True, timeout: float = 30):
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, method=method, headers=hdrs)
    if follow:
        opener = urllib.request.build_opener()
    else:
        # A no-redirect opener so we can read the *first* response headers
        # (Hugging Face puts X-Linked-Etag = sha256 there, before the CDN hop).
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        opener = urllib.request.build_opener(_NoRedirect)
    return opener.open(req, timeout=timeout)


def _get_json(url: str, headers: Optional[dict] = None, timeout: float = 30) -> dict:
    with _request(url, "GET", headers, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
def load_manifest() -> dict:
    try:
        data = json.loads(MANIFEST_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_manifest(data: dict) -> None:
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_FILE.write_text(json.dumps(data, indent=2))


def get_source(path) -> Optional[dict]:
    return load_manifest().get(_key(path))


def set_source(path, entry: dict) -> None:
    data = load_manifest()
    cur = data.get(_key(path), {})
    cur.update(entry)
    data[_key(path)] = cur
    save_manifest(data)


def forget(path) -> None:
    data = load_manifest()
    data.pop(_key(path), None)
    save_manifest(data)


# --------------------------------------------------------------------------- #
# identify / set source
# --------------------------------------------------------------------------- #
def identify_civitai(path, progress_cb: Optional[Callable[[float], None]] = None) -> dict:
    """Hash the file and ask Civitai to identify it. Records source on success."""
    sha = sha256_file(path, progress_cb)
    try:
        mv = _get_json(CIVITAI_BY_HASH.format(sha=sha))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"found": False, "sha256": sha, "detail": "Not found on Civitai"}
        raise
    entry = {
        "source": "civitai",
        "sha256": sha,
        "civitai": {
            "modelId": mv.get("modelId"),
            "modelVersionId": mv.get("id"),
            "versionName": mv.get("name", ""),
        },
    }
    set_source(path, entry)
    return {"found": True, "sha256": sha, "modelId": mv.get("modelId"),
            "versionName": mv.get("name", ""), "detail": "Identified on Civitai"}


def _hf_parse(repo_or_url: str) -> str:
    """Accept a bare repo id (org/name) or a huggingface.co URL -> repo id."""
    s = repo_or_url.strip()
    if s.startswith("http"):
        parts = urllib.parse.urlparse(s).path.strip("/").split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    return s


def resolve_hf(path, repo_or_url: str, revision: str = "main",
               filename: Optional[str] = None) -> dict:
    """Find this file inside a Hugging Face repo (by basename) and record it."""
    repo = _hf_parse(repo_or_url)
    want = filename or Path(path).name
    tree = _get_json(HF_TREE.format(repo=repo, rev=revision))
    match = None
    for item in tree if isinstance(tree, list) else []:
        if item.get("type") == "file" and Path(item.get("path", "")).name == want:
            match = item
            break
    if not match:
        return {"found": False, "detail": f"'{want}' not found in {repo}@{revision}"}
    entry = {
        "source": "huggingface",
        "huggingface": {"repo_id": repo, "path": match["path"], "revision": revision},
    }
    # Record the repo's current sha for reference only — NOT as the local sha
    # (the local file might be an older version; its real sha is computed on
    # first check_update and cached then).
    lfs = match.get("lfs") or {}
    if lfs.get("oid"):
        entry["hf_repo_oid"] = lfs["oid"]
    set_source(path, entry)
    return {"found": True, "repo": repo, "path": match["path"], "detail": "Linked to Hugging Face"}


def set_url(path, url: str) -> dict:
    """Record a direct download URL as the source (captures etag/size now)."""
    etag = size = last_mod = None
    try:
        with _request(url, "HEAD") as r:
            etag = r.headers.get("ETag")
            size = int(r.headers.get("Content-Length") or 0) or None
            last_mod = r.headers.get("Last-Modified")
    except Exception:
        pass
    set_source(path, {"source": "url", "url": {"url": url, "etag": etag,
                                               "size": size, "last_modified": last_mod}})
    return {"found": True, "detail": "Linked to URL"}


# --------------------------------------------------------------------------- #
# check for updates
# --------------------------------------------------------------------------- #
def _civitai_headers() -> dict:
    key = config.get("civitai_api_key")
    return {"Authorization": f"Bearer {key}"} if key else {}


def _hf_remote_sha(repo: str, path_in_repo: str, revision: str):
    """(sha256, size) of an HF file from the first (non-CDN) response headers."""
    url = HF_RESOLVE.format(repo=repo, rev=revision, path=urllib.parse.quote(path_in_repo))
    try:
        with _request(url, "HEAD", follow=False) as r:
            headers = r.headers
    except urllib.error.HTTPError as e:
        headers = e.headers  # the 302 carries X-Linked-Etag / X-Linked-Size
    sha = headers.get("X-Linked-Etag") or headers.get("ETag") or ""
    sha = sha.strip('"').lower()
    size = headers.get("X-Linked-Size") or headers.get("Content-Length")
    return (sha if len(sha) == 64 else None, int(size) if size else None)


def check_update(path) -> dict:
    """Determine whether a newer version exists for this model's source."""
    src = get_source(path)
    base = {"source": (src or {}).get("source", "unknown"), "known": bool(src),
            "available": None, "current": "", "latest": "", "detail": "",
            "download_url": None, "expected_sha": None, "expected_size": None,
            "error": None}
    if not src:
        base["detail"] = "No source set"
        return base
    try:
        kind = src["source"]
        if kind == "huggingface":
            hf = src["huggingface"]
            remote_sha, remote_size = _hf_remote_sha(hf["repo_id"], hf["path"], hf.get("revision", "main"))
            local_sha = src.get("sha256") or sha256_file(path)
            set_source(path, {"sha256": local_sha})
            base["current"] = local_sha[:12]
            base["latest"] = (remote_sha or "?")[:12]
            base["available"] = bool(remote_sha and remote_sha != local_sha.lower())
            base["download_url"] = HF_RESOLVE.format(
                repo=hf["repo_id"], rev=hf.get("revision", "main"),
                path=urllib.parse.quote(hf["path"]))
            base["expected_sha"] = remote_sha
            base["expected_size"] = remote_size
            base["detail"] = "Update available" if base["available"] else "Up to date"

        elif kind == "civitai":
            cv = src["civitai"]
            model = _get_json(CIVITAI_MODEL.format(id=cv["modelId"]), _civitai_headers())
            versions = model.get("modelVersions", [])
            if not versions:
                base["error"] = "No versions returned"
                return base
            latest = versions[0]
            base["current"] = cv.get("versionName", str(cv.get("modelVersionId")))
            base["latest"] = latest.get("name", str(latest.get("id")))
            base["available"] = latest.get("id") != cv.get("modelVersionId")
            files = latest.get("files", [])
            primary = next((f for f in files if f.get("primary")), files[0] if files else None)
            if primary:
                base["download_url"] = primary.get("downloadUrl")
                base["expected_sha"] = (primary.get("hashes", {}) or {}).get("SHA256", "").lower() or None
                base["expected_size"] = int(primary.get("sizeKB", 0) * 1024) or None
            base["detail"] = "Update available" if base["available"] else "Up to date"

        elif kind == "url":
            u = src["url"]
            etag = size = last_mod = None
            with _request(u["url"], "HEAD") as r:
                etag = r.headers.get("ETag")
                size = int(r.headers.get("Content-Length") or 0) or None
                last_mod = r.headers.get("Last-Modified")
            changed = (etag != u.get("etag")) or (size != u.get("size")) or (last_mod != u.get("last_modified"))
            base["current"] = (u.get("etag") or u.get("last_modified") or "recorded")
            base["latest"] = (etag or last_mod or "current")
            base["available"] = bool(changed)
            base["download_url"] = u["url"]
            base["expected_size"] = size
            base["detail"] = "Update available" if changed else "Up to date"
        else:
            base["detail"] = "Unknown source type"
    except Exception as exc:  # noqa: BLE001
        base["error"] = str(exc)
        base["detail"] = f"Check failed: {exc}"
    return base


# --------------------------------------------------------------------------- #
# download + atomic replace
# --------------------------------------------------------------------------- #
def _download(url: str, dest: Path, headers: Optional[dict],
              progress_cb: Optional[Callable[[str, float], None]]) -> int:
    tmp = dest.with_suffix(dest.suffix + ".laih-download")
    with _request(url, "GET", headers, timeout=60) as r:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with tmp.open("wb") as fh:
            while True:
                chunk = r.read(8 * 1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb("downloading", done / total)
    return tmp, done


def update_model(path, progress_cb: Optional[Callable[[str, float], None]] = None) -> dict:
    """Check, then (if newer) download and atomically replace the file."""
    dest = Path(path)
    st = check_update(path)
    if st.get("error"):
        return {"updated": False, "reason": st["error"]}
    if not st.get("available"):
        return {"updated": False, "reason": "Already up to date"}
    url = st.get("download_url")
    if not url:
        return {"updated": False, "reason": "No download URL available"}

    headers = _civitai_headers() if st["source"] == "civitai" else None
    if progress_cb:
        progress_cb("starting", 0.0)
    tmp, size = _download(url, dest, headers, progress_cb)

    # verify before replacing the real file
    if st.get("expected_size") and size != st["expected_size"]:
        tmp.unlink(missing_ok=True)
        return {"updated": False, "reason": f"size mismatch (got {size}, expected {st['expected_size']})"}
    if st.get("expected_sha"):
        if progress_cb:
            progress_cb("verifying", 1.0)
        got = sha256_file(tmp)
        if got.lower() != st["expected_sha"].lower():
            tmp.unlink(missing_ok=True)
            return {"updated": False, "reason": "checksum mismatch — file not replaced"}
        new_sha = got
    else:
        new_sha = None

    os.replace(tmp, dest)  # atomic
    updates = {}
    if new_sha:
        updates["sha256"] = new_sha
    if st["source"] == "url":
        updates["url"] = {**(get_source(path) or {}).get("url", {})}
    set_source(path, updates or {"sha256": st.get("expected_sha")})
    return {"updated": True, "reason": f"Updated to {st.get('latest') or 'latest'}", "sha256": new_sha}
