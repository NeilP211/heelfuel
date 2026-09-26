"""Write the static site: one HTML page with the day's data inlined, plus the raw JSON."""

from __future__ import annotations

import json
import os
import shutil

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
PLACEHOLDER = "/*__HEELFUEL_DATA__*/null"
_DASHES = {chr(0x2013): "-", chr(0x2014): "-"}


def _json_for_script(payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    for bad, good in _DASHES.items():
        text = text.replace(bad, good)
    # Keep the payload from closing its own <script> tag or starting an HTML comment.
    return text.replace("</", "<\\/").replace("<!--", "<\\!--")


def render_site(payload: dict, out_dir: str) -> str:
    os.makedirs(os.path.join(out_dir, "data"), exist_ok=True)
    with open(os.path.join(WEB_DIR, "index.html"), encoding="utf-8") as f:
        template = f.read()
    if PLACEHOLDER not in template:
        raise RuntimeError("web/index.html is missing the data placeholder")
    html = template.replace(PLACEHOLDER, _json_for_script(payload))
    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(out_dir, "data", "latest.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    for name in os.listdir(WEB_DIR):
        if name != "index.html":
            src = os.path.join(WEB_DIR, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(out_dir, name))
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    return path
