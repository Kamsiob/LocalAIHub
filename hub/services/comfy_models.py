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
from .comfyui import MODEL_CATEGORIES, MODEL_EXTS, MODELS_DIR, _human_size

MANIFEST_FILE = config.CONFIG_DIR / "comfy_models.json"
USER_AGENT = "local-ai-hub/1.0 (+https://github.com/Kamsiob/local-ai-hub)"

CIVITAI_BY_HASH = "https://civitai.com/api/v1/model-versions/by-hash/{sha}"
CIVITAI_MODEL = "https://civitai.com/api/v1/models/{id}"
CIVITAI_VERSION = "https://civitai.com/api/v1/model-versions/{vid}"
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
            # No Civitai match. Record a lightweight "untracked" marker so the UI
            # can show "installed, no update source" instead of silently reverting
            # to "Set source". Any real source set later takes precedence.
            set_source(path, {"untracked": True, "detail": "No match on Civitai"})
            return {"found": False, "sha256": sha, "detail": "No match on Civitai"}
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
    """(sha256, size) of an HF file from the first (non-CDN) response headers.

    Returns (None, None) if the file doesn't exist (404) or is unreachable — the
    caller treats that as "not found" rather than trusting a 404 body's length.
    """
    url = HF_RESOLVE.format(repo=repo, rev=revision, path=urllib.parse.quote(path_in_repo))
    try:
        with _request(url, "HEAD", follow=False) as r:
            status, headers = r.status, r.headers
    except urllib.error.HTTPError as e:
        status, headers = e.code, e.headers  # a 302 carries X-Linked-Etag / X-Linked-Size
    if status not in (200, 301, 302, 303, 307, 308):
        return (None, None)  # 404 etc. — do NOT read the error body's Content-Length
    sha = (headers.get("X-Linked-Etag") or (headers.get("ETag") if status == 200 else "") or "").strip('"').lower()
    # X-Linked-Size is authoritative for LFS files; Content-Length is only the real
    # file size on a direct 200 (on a 302 it's the redirect page, not the model).
    size = headers.get("X-Linked-Size") or (headers.get("Content-Length") if status == 200 else None)
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


# --------------------------------------------------------------------------- #
# install a NEW model (download -> verify -> place in the right folder)
# --------------------------------------------------------------------------- #
VALID_CATEGORIES = {c[0] for c in MODEL_CATEGORIES}

# Civitai model type -> one of our five ComfyUI folders (None = must ask).
_CIVITAI_TYPE_TO_CAT = {
    "Checkpoint": "checkpoints",
    "LORA": "loras",
    "LoCon": "loras",
    "DoRA": "loras",
    "VAE": "vae",
    # TextualInversion (embeddings), Controlnet, Upscaler, etc. -> not one of the
    # five; leave None so the user is asked rather than guessing wrong.
}


def _category_from_path(p: str):
    """Best-effort folder from a repo path / filename; None if unsure."""
    s = (p or "").lower().replace("\\", "/")
    for seg in s.split("/"):
        if seg in VALID_CATEGORIES:
            return seg
    if any(k in s for k in ("text_encoder", "clip_", "/clip", "t5xxl", "umt5")):
        return "text_encoders"
    if "vae" in s:
        return "vae"
    if "lora" in s:
        return "loras"
    if "checkpoint" in s:
        return "checkpoints"
    if any(k in s for k in ("unet", "diffusion_model", "/diffusion")):
        return "diffusion_models"
    return None


def _parse_hf_url(url: str):
    """(repo, revision, in-repo path) from a huggingface.co blob/resolve URL."""
    parts = urllib.parse.urlparse(url).path.strip("/").split("/")
    # <org>/<name>/(blob|resolve)/<rev>/<path...>
    if len(parts) >= 5 and parts[2] in ("blob", "resolve"):
        repo = f"{parts[0]}/{parts[1]}"
        rev = parts[3]
        path = "/".join(parts[4:])
        return repo, rev, urllib.parse.unquote(path)
    return None, None, None


def analyze_install(link: str) -> dict:
    """Inspect a link and return everything needed to install it (no download).

    Returns {ok, source, filename, size, size_human, download_url, expected_sha,
    expected_size, category, category_reason, provenance, error}. category is None
    when it can't be determined — the caller must then ask the user.
    """
    out = {"ok": False, "source": None, "filename": "", "size_human": "",
           "download_url": None, "expected_sha": None, "expected_size": None,
           "category": None, "category_reason": "", "provenance": {}, "error": None}
    link = (link or "").strip()
    if not link.startswith("http"):
        out["error"] = "Please paste a full http(s) link."
        return out
    host = urllib.parse.urlparse(link).netloc.lower()
    try:
        if "civitai.com" in host:
            out["source"] = "civitai"
            q = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
            path_parts = urllib.parse.urlparse(link).path.strip("/").split("/")
            vid = None
            if "modelVersionId" in q:
                vid = q["modelVersionId"][0]
            elif "download" in path_parts and "models" in path_parts:
                vid = path_parts[-1]
            if vid:
                ver = _get_json(CIVITAI_VERSION.format(vid=vid), _civitai_headers())
            else:
                mid = next((p for p in path_parts if p.isdigit()), None)
                if not mid:
                    out["error"] = "Could not find a Civitai model id in that link."
                    return out
                model = _get_json(CIVITAI_MODEL.format(id=mid), _civitai_headers())
                vers = model.get("modelVersions", [])
                if not vers:
                    out["error"] = "That Civitai model has no downloadable versions."
                    return out
                ver = vers[0]
                ver.setdefault("model", {})["type"] = model.get("type")
            files = ver.get("files", [])
            primary = next((f for f in files if f.get("primary")), files[0] if files else None)
            if not primary:
                out["error"] = "No files on that Civitai version."
                return out
            ctype = (ver.get("model") or {}).get("type")
            out["filename"] = primary.get("name", "model.safetensors")
            out["download_url"] = primary.get("downloadUrl")
            out["expected_sha"] = (primary.get("hashes", {}) or {}).get("SHA256", "").lower() or None
            out["expected_size"] = int(primary.get("sizeKB", 0) * 1024) or None
            out["category"] = _CIVITAI_TYPE_TO_CAT.get(ctype) or _category_from_path(out["filename"])
            out["category_reason"] = f"Civitai type: {ctype}" if ctype else "from filename"
            out["provenance"] = {"source": "civitai", "civitai": {
                "modelId": ver.get("modelId"), "modelVersionId": ver.get("id"),
                "versionName": ver.get("name", "")}}

        elif "huggingface.co" in host:
            out["source"] = "huggingface"
            repo, rev, path = _parse_hf_url(link)
            if not repo:
                out["error"] = "Use a link to a specific file (…/resolve/… or …/blob/…)."
                return out
            out["filename"] = os.path.basename(path)
            sha, size = _hf_remote_sha(repo, path, rev)
            if sha is None and size is None:
                out["error"] = f"File not found on Hugging Face: {repo}@{rev}/{path} (check the path and branch)."
                return out
            out["download_url"] = HF_RESOLVE.format(repo=repo, rev=rev, path=urllib.parse.quote(path))
            out["expected_sha"] = sha
            out["expected_size"] = size
            out["category"] = _category_from_path(path)
            out["category_reason"] = "from repo path"
            out["provenance"] = {"source": "huggingface",
                                 "huggingface": {"repo_id": repo, "path": path, "revision": rev}}

        else:
            out["source"] = "url"
            path = urllib.parse.urlparse(link).path
            out["filename"] = os.path.basename(path) or "model.bin"
            out["download_url"] = link
            try:
                with _request(link, "HEAD") as r:
                    out["expected_size"] = int(r.headers.get("Content-Length") or 0) or None
                    etag = r.headers.get("ETag")
            except Exception:
                etag = None
            out["category"] = _category_from_path(out["filename"])
            out["category_reason"] = "from filename"
            out["provenance"] = {"source": "url", "url": {"url": link, "etag": etag,
                                                          "size": out["expected_size"]}}

        if out["expected_size"]:
            out["size_human"] = _human_size(out["expected_size"])
        if Path(out["filename"]).suffix.lower() not in MODEL_EXTS:
            out["category_reason"] += " (unrecognized extension)"
        out["ok"] = bool(out["download_url"])
        if not out["ok"]:
            out["error"] = "Could not resolve a download URL."
    except urllib.error.HTTPError as e:
        out["error"] = f"{e.code} {e.reason}"
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    return out


def install_model(link: str, category: str,
                  progress_cb: Optional[Callable[[str, float], None]] = None) -> dict:
    """Download the model at `link` and place it in models/<category>/."""
    if category not in VALID_CATEGORIES:
        return {"ok": False, "error": f"Unknown target folder: {category}"}
    info = analyze_install(link)
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error") or "Could not analyze that link."}

    filename = os.path.basename(info["filename"])
    if not filename or filename in (".", ".."):
        return {"ok": False, "error": "Could not determine a safe filename."}
    dest_dir = MODELS_DIR / category
    dest = dest_dir / filename
    if dest.exists():
        return {"ok": False, "error": f"{filename} already exists in {category}."}
    dest_dir.mkdir(parents=True, exist_ok=True)

    headers = _civitai_headers() if info["source"] == "civitai" else None
    if progress_cb:
        progress_cb("starting", 0.0)
    tmp, size = _download(info["download_url"], dest, headers, progress_cb)

    if info.get("expected_size") and size != info["expected_size"]:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "error": f"size mismatch (got {size}, expected {info['expected_size']})"}
    new_sha = None
    if info.get("expected_sha"):
        if progress_cb:
            progress_cb("verifying", 1.0)
        got = sha256_file(tmp)
        if got.lower() != info["expected_sha"].lower():
            tmp.unlink(missing_ok=True)
            return {"ok": False, "error": "checksum mismatch — file discarded"}
        new_sha = got

    os.replace(tmp, dest)  # atomic
    prov = dict(info.get("provenance") or {})
    if new_sha:
        prov["sha256"] = new_sha
    set_source(str(dest), prov)  # so it's immediately update-trackable
    return {"ok": True, "path": str(dest), "category": category, "filename": filename}
