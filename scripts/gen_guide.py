"""Generate docs/GETTING_STARTED.md from hub/guide.py (the single source).

Run after editing hub/guide.py:  python3 scripts/gen_guide.py
The in-app screen renders the same GUIDE via Backend.get_guide, so the two
stay in sync.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hub.guide import GUIDE  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "docs", "GETTING_STARTED.md")


def render_block(b) -> str:
    t = b["type"]
    if t == "p":
        lines = b["text"].split("\n")
        # lines starting with a bullet become a markdown list
        if any(l.strip().startswith("•") for l in lines):
            return "\n".join(("- " + l.strip()[1:].strip()) if l.strip().startswith("•") else l
                             for l in lines)
        return "  \n".join(lines)  # preserve intra-paragraph line breaks
    if t == "h":
        return f"#### {b['text']}"
    if t == "code":
        return f"```{b.get('lang', '')}\n{b['code']}\n```"
    if t == "warn":
        return "> ⚠️ **Watch out:** " + b["text"].replace("\n", "\n> ")
    if t == "note":
        return "> ℹ️ **Note:** " + b["text"].replace("\n", "\n> ")
    return b.get("text", "")


def main() -> None:
    out = [f"# {GUIDE['title']}", "", f"*{GUIDE['subtitle']}*", ""]
    for b in GUIDE["intro"]:
        out += [render_block(b), ""]
    for track in GUIDE["tracks"]:
        out += ["---", "", f"## Track {track['label']}", ""]
        for b in track.get("blocks", []):
            out += [render_block(b), ""]
        for sec in track.get("sections", []):
            out += [f"### {sec['title']}", ""]
            for b in sec["blocks"]:
                out += [render_block(b), ""]
    out += ["---", "",
            "*This guide is generated from `hub/guide.py`; the in-app Getting Started "
            "screen renders the same content. Edit the source, then run "
            "`python3 scripts/gen_guide.py`.*", ""]
    with open(OUT, "w") as f:
        f.write("\n".join(out))
    print(f"wrote {OUT} ({len(out)} lines)")


if __name__ == "__main__":
    main()
