#!/usr/bin/env python3
"""
Build a single self-contained preview.html by inlining styles.css, app.js and
data/evidence.json into one file. Useful for:
  * a live shareable preview / Artifact,
  * an offline snapshot you can open by double-clicking (no server needed).

Note: the inlined data is a snapshot; the deployed site always reads the live
data/evidence.json. Regenerate with:  python scripts/build_preview.py
"""
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
html = (ROOT / "index.html").read_text(encoding="utf-8")
css = (ROOT / "styles.css").read_text(encoding="utf-8")
appjs = (ROOT / "app.js").read_text(encoding="utf-8")
data = json.loads((ROOT / "data" / "evidence.json").read_text(encoding="utf-8"))

# body inner
body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
body = body.replace('<script src="app.js"></script>', "")

data_js = json.dumps(data, ensure_ascii=False)

# 1) full standalone document (open by double-click, no server)
standalone = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Ebola (Bundibugyo) Evidence Dashboard</title>
<style>
{css}
</style>
</head>
<body>
{body}
<script>window.__EVIDENCE__ = {data_js};</script>
<script>
{appjs}
</script>
</body>
</html>
"""
(ROOT / "preview.html").write_text(standalone, encoding="utf-8")

# 2) content-only version for the Artifact tool (it supplies the skeleton)
artifact = f"""<title>Ebola Evidence Watch</title>
<style>
{css}
</style>
{body}
<script>window.__EVIDENCE__ = {data_js};</script>
<script>
{appjs}
</script>
"""
(ROOT.parent / "artifact_preview.html").write_text(artifact, encoding="utf-8")

print(f"Wrote preview.html ({len(standalone)//1024} KB) and "
      f"../artifact_preview.html ({len(artifact)//1024} KB) — {data['record_count']} records")
