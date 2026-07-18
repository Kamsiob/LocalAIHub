"""End-to-end verification of ComfyUI model updates through the real UI.

Drives the actual app: expand ComfyUI, open the source modal on a real model,
link it to its real Hugging Face repo, then check for updates — asserting the
manifest and the DOM both reflect each step. The 20 GB local hash is seeded (set
equal to the real remote sha) so the check is fast; that's the only shortcut.
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --no-sandbox"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app as appmod  # noqa: E402
from hub.services import comfy_models as cm  # noqa: E402

REPO = "Comfy-Org/Qwen-Image-Edit_ComfyUI"
FNAME = "qwen_image_edit_2509_fp8_e4m3fn.safetensors"

results = []
def check(name, cond, detail=""):
    results.append(bool(cond))
    print(("PASS" if cond else "FAIL"), "|", name, ("— " + str(detail)) if detail else "")

application = QApplication(sys.argv)
win = appmod.MainWindow()
win.resize(780, 1000)
win.show()
page = win.view.page()
MPATH = str((win.backend.comfyui.models_dir / "diffusion_models" / FNAME).resolve())
cm.forget(MPATH)  # start clean

def js(code, cb=None):
    page.runJavaScript(code, cb or (lambda _: None))


def s1():
    js("document.querySelector('.card[data-svc=comfyui] .chevron').click()")


def s2():
    # open the source modal on our target model row
    js(f"var b=[...document.querySelectorAll('[data-act=csource]')].find(x=>x.dataset.name && x.dataset.name.indexOf('{FNAME}')>=0); if(b)b.click(); (b?1:0)",
       lambda r: check("modal opens on target row's Set source", r == 1))
    js("document.getElementById('sourceModal').classList.contains('show')",
       lambda v: check("modal is visible", v))


def s3():
    # fill HF repo + click Link (real backend.comfy_set_hf)
    js(f"document.getElementById('smHf').value='{REPO}'; document.getElementById('smHfBtn').click(); true")
    print(">> linked to Hugging Face; waiting for resolve…")


def s4():
    src = cm.get_source(MPATH)
    check("manifest source set to huggingface", (src or {}).get("source") == "huggingface", (src or {}).get("source"))
    check("HF path resolved in repo tree", "path" in (src or {}).get("huggingface", {}),
          (src or {}).get("huggingface"))
    js("var b=[...document.querySelectorAll('[data-act=ccheck]')].length; b",
       lambda n: check("a 'Check' button now exists", (n or 0) >= 1, f"count={n}"))
    # seed local sha = real remote sha so the check is instant (skip 20GB hash)
    sha, _ = cm._hf_remote_sha(REPO, cm.get_source(MPATH)["huggingface"]["path"], "main")
    cm.set_source(MPATH, {"sha256": sha})
    print(">> seeded local sha; clicking Check…")
    js(f"var b=[...document.querySelectorAll('[data-act=ccheck]')].find(x=>x.dataset.path==='{MPATH}'); if(b)b.click(); (b?1:0)",
       lambda r: check("clicked Check on target", r == 1))


def s5():
    src = cm.get_source(MPATH)
    lc = (src or {}).get("last_check") or {}
    check("check recorded (up to date)", lc.get("available") is False, lc)
    js(f"(function(){{var rows=[...document.querySelectorAll('.model')];var r=rows.find(x=>x.querySelector('.model-name') && x.querySelector('.model-name').title.indexOf('{FNAME}')>=0);return r?(r.querySelector('.cu-uptodate')?'uptodate':(r.querySelector('[data-act=cupdate]')?'update':'other')):'none';}})()",
       lambda v: check("row shows 'Up to date' in the UI", v == "uptodate", v))


def s6():
    cm.forget(MPATH)  # clean up test provenance
    print(f"\n=== {sum(results)}/{len(results)} checks passed ===")
    application.exit(0 if all(results) else 1)


for fn, t in [(s1, 3000), (s2, 4500), (s3, 5500), (s4, 9000), (s5, 12000), (s6, 14000)]:
    QTimer.singleShot(t, fn)
QTimer.singleShot(20000, lambda: application.exit(2))
sys.exit(application.exec())
