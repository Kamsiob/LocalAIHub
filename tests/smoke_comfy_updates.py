"""Smoke test for hub.services.comfy_models against the real HF + Civitai APIs.

Cheap by design: uses hash lookups and HEAD requests (no multi-GB downloads),
plus one tiny real download to prove the download/verify/replace pipeline.
Nothing here touches the user's actual model files.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from hub.services import comfy_models as cm  # noqa: E402

tmp = Path(tempfile.mkdtemp())


def hr(t):
    print(f"\n=== {t} ===")


# ---- Hugging Face check (uses the user's own model repo, HEAD only) --------
hr("Hugging Face: remote sha + size via HEAD (no download)")
repo = "Comfy-Org/Qwen-Image-Edit_ComfyUI"
pth = "split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors"
try:
    sha, size = cm._hf_remote_sha(repo, pth, "main")
    print(f"  remote sha256: {sha}")
    print(f"  remote size  : {size} bytes ({(size or 0)/1e9:.1f} GB)")
    # simulate a local file already at that sha -> "up to date"
    f = tmp / "qwen_edit.safetensors"
    f.write_bytes(b"x")
    cm.set_source(f, {"source": "huggingface",
                      "huggingface": {"repo_id": repo, "path": pth, "revision": "main"},
                      "sha256": sha})
    st = cm.check_update(f)
    print(f"  check (local==remote): available={st['available']} — {st['detail']}")
    # simulate an out-of-date local file
    cm.set_source(f, {"sha256": "0" * 64})
    st2 = cm.check_update(f)
    print(f"  check (local stale)  : available={st2['available']} — {st2['detail']}")
    print(f"  download_url present : {bool(st2['download_url'])}")
except Exception as e:
    print(f"  HF test error: {e}")


# ---- Civitai identify-by-hash + version check -----------------------------
hr("Civitai: by-hash identify + latest-version check")
try:
    # bootstrap a real hash from the public API (a popular LoRA)
    listing = cm._get_json("https://civitai.com/api/v1/models?limit=1&types=LORA&sort=Most%20Downloaded")
    item = listing["items"][0]
    ver = item["modelVersions"][0]
    sha = (ver["files"][0]["hashes"] or {}).get("SHA256")
    print(f"  sample model: '{item['name']}' v'{ver['name']}' modelId={item['id']}")
    print(f"  file sha256 : {sha}")
    byhash = cm._get_json(cm.CIVITAI_BY_HASH.format(sha=sha))
    print(f"  by-hash -> modelId={byhash.get('modelId')} versionId={byhash.get('id')} (matches={byhash.get('modelId')==item['id']})")
    # simulate a local file pinned to the OLDEST version -> update available
    versions = item["modelVersions"]
    oldest = versions[-1]
    f = tmp / "some_lora.safetensors"
    f.write_bytes(b"x")
    cm.set_source(f, {"source": "civitai",
                      "civitai": {"modelId": item["id"], "modelVersionId": oldest["id"],
                                  "versionName": oldest["name"]}})
    st = cm.check_update(f)
    nver = len(versions)
    print(f"  model has {nver} version(s); pinned to oldest -> available={st['available']} (current='{st['current']}' latest='{st['latest']}')")
    print(f"  download_url present : {bool(st['download_url'])}, expected_sha set: {bool(st['expected_sha'])}")
except Exception as e:
    print(f"  Civitai test error: {e}")


# ---- download + verify + atomic replace (tiny real file) ------------------
hr("Download + sha + atomic replace (tiny file, real network)")
try:
    dest = tmp / "config.json"
    dest.write_bytes(b"OLD CONTENT")
    old = dest.read_bytes()
    url = "https://huggingface.co/hf-internal-testing/tiny-random-bert/resolve/main/config.json"
    tmpfile, size = cm._download(url, dest, None, lambda s, f: None)
    got_sha = cm.sha256_file(tmpfile)
    print(f"  downloaded {size} bytes, sha256={got_sha[:16]}…")
    import os
    os.replace(tmpfile, dest)
    print(f"  atomic replace ok: content changed = {dest.read_bytes() != old}")
except Exception as e:
    print(f"  download test error: {e}")

print("\nDONE — HF check, Civitai identify+check, and download/replace exercised against real services.")
import shutil  # noqa: E402
shutil.rmtree(tmp, ignore_errors=True)
