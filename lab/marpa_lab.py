# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "pillow", "numpy", "opencv-python-headless", "pydeck"]
# ///
"""
MARPA LAB — sketch-to-model laboratory
Run:  FAL_KEY=... uv run marimo edit marpa_lab.py
Slides: in the marimo editor, bottom-right layout toggle -> Slides. Each cell = one station.
Every station writes to the shared artifact ledger; any artifact can feed any other station.
"""
import marimo

__generated_with = "0.9.0"
app = marimo.App(width="full")


@app.cell
def __():
    import marimo as mo
    import os, json, base64, time, urllib.request, urllib.error, hashlib
    from pathlib import Path
    import numpy as np
    from PIL import Image

    LAB = Path(__file__).parent / "lab_artifacts"
    LAB.mkdir(exist_ok=True)
    LEDGER = LAB / "ledger.jsonl"
    FAL_KEY = os.environ.get("FAL_KEY", "")

    def log_artifact(kind, path, meta):
        rec = {"ts": time.time(), "kind": kind, "path": str(path), **meta}
        with open(LEDGER, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec

    def ledger_rows():
        if not LEDGER.exists():
            return []
        return [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]

    def data_uri(p: Path):
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "glb": "model/gltf-binary", "mp4": "video/mp4"}.get(p.suffix[1:].lower(), "application/octet-stream")
        return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()

    def fal_sync(endpoint, payload, timeout=300):
        req = urllib.request.Request(
            f"https://fal.run/{endpoint}", data=json.dumps(payload).encode(),
            headers={"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def fal_queue(endpoint, payload, poll=4, timeout=900):
        """queue API for long jobs (video)."""
        req = urllib.request.Request(
            f"https://queue.fal.run/{endpoint}", data=json.dumps(payload).encode(),
            headers={"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            sub = json.loads(r.read())
        status_url, resp_url = sub["status_url"], sub["response_url"]
        t0 = time.time()
        while time.time() - t0 < timeout:
            with urllib.request.urlopen(urllib.request.Request(
                    status_url, headers={"Authorization": f"Key {FAL_KEY}"}), timeout=30) as r:
                st = json.loads(r.read())
            if st.get("status") == "COMPLETED":
                with urllib.request.urlopen(urllib.request.Request(
                        resp_url, headers={"Authorization": f"Key {FAL_KEY}"}), timeout=60) as r:
                    return json.loads(r.read())
            if st.get("status") in ("FAILED", "ERROR"):
                raise RuntimeError(st)
            time.sleep(poll)
        raise TimeoutError(endpoint)

    def save_result_image(resp, stem):
        imgs = resp.get("images") or ([resp["image"]] if "image" in resp else [])
        out = []
        for i, im in enumerate(imgs):
            url = im["url"] if isinstance(im, dict) else im
            raw = (base64.b64decode(url.split(",", 1)[1]) if url.startswith("data:")
                   else urllib.request.urlopen(url, timeout=180).read())
            p = LAB / f"{stem}_{i}.png"
            p.write_bytes(raw)
            out.append(p)
        return out

    FULL = "height: 86vh; overflow:auto;"  # station viewport
    mo.md("# MARPA LAB").center()
    return (mo, os, json, base64, time, urllib, hashlib, Path, np, Image,
            LAB, LEDGER, FAL_KEY, log_artifact, ledger_rows, data_uri,
            fal_sync, fal_queue, save_result_image, FULL)


@app.cell
def __(mo, LAB, Path):
    # ---------- STATION 0 · SOURCE ----------
    _imgs = sorted([p for p in LAB.glob("*.png")] + [p for p in LAB.glob("*.jpg")])
    _proj = Path(__file__).parent
    _extra = sorted(list(_proj.glob("*.png"))[:40])
    source_pick = mo.ui.dropdown(
        options={p.name: str(p) for p in (_extra + _imgs)} or {"(drop images beside this notebook)": ""},
        label="Source image")
    source_upload = mo.ui.file(kind="area", filetypes=[".png", ".jpg", ".jpeg"], label="…or drop a file")
    mo.vstack([mo.md("## 0 · SOURCE — pick the working image"), source_pick, source_upload])
    return source_pick, source_upload


@app.cell
def __(mo, LAB, Path, source_pick, source_upload, data_uri, FULL):
    import time as _t
    if source_upload.value:
        _p = LAB / f"upload_{int(_t.time())}{Path(source_upload.value[0].name).suffix}"
        _p.write_bytes(source_upload.value[0].contents)
        SRC = _p
    elif source_pick.value:
        SRC = Path(source_pick.value)
    else:
        SRC = None
    mo.Html(f'<div style="{FULL}text-align:center">'
            + (f'<img src="{data_uri(SRC)}" style="max-height:80vh;max-width:100%;'
               f'border:1px solid #ccc"/><p><code>{SRC}</code></p>' if SRC
               else "<h2>no source selected</h2>") + "</div>")
    return (SRC,)


@app.cell
def __(mo):
    # ---------- STATION 1 · IMAGE GEN controls ----------
    IMG_MODELS = {
        "Nano Banana Pro (edit)": "fal-ai/nano-banana-pro/edit",
        "Nano Banana (edit)": "fal-ai/nano-banana/edit",
        "FLUX Kontext Pro (edit)": "fal-ai/flux-pro/kontext",
        "Seedream v4 (edit)": "fal-ai/bytedance/seedream/v4/edit",
        "Qwen Image Edit": "fal-ai/qwen-image-edit",
    }
    gen_model = mo.ui.dropdown(options=IMG_MODELS, value="Nano Banana Pro (edit)", label="model")
    PROMPT_PRESETS = {
        "— custom —": "",
        "P1 line plan": "Redraw as a clean monochrome construction-document plan, black linework on white, CAD conventions, double-line walls, dashed planting-bed outlines, tree circles with center dot. Preserve exact layout. No text, labels, or numbers.",
        "P2 watercolor hero": "Museum-quality landscape architecture presentation plan, watercolor wash with marker and fine ink on cold-press paper, species-differentiated canopies with soft lower-right shadows, luminous water, restrained naturalistic palette. Preserve exact layout and element count. No text.",
        "P3 species-true": "Refine planting color only: Colorado blue spruce silvery blue-green, redbud and crabapple soft rose-pink, golden Hakone grass chartreuse blades, serviceberry copper, catmint lavender drifts at bed edges. Keep layout, linework, water, and paths exactly unchanged. No text.",
        "P6 figure-ground": "Redraw as a figure-ground diagram: buildings solid black, hardscape mid-gray, all planting and lawn white, property line thin black. Flat, no texture, no shadows. Preserve exact layout. No text.",
        "P7 class-color map": "Repaint as a flat segmentation map, one solid color per material, hard edges, no gradients or texture: trees pure green, lawn light green, water blue, hardscape orange, buildings gray, planting beds purple, background white. Preserve every element's exact position and shape. No text.",
        "P8 isolate trees": "Remove everything except the tree canopies; pure white background; keep every canopy in its exact position, size, and color. No text.",
        "P9 blueprint": "Redraw as a classic blueprint: white linework on Prussian-blue ground, fine consistent line weight, subtle paper grain. Preserve exact layout. No text.",
        "P10 CD hatch": "Construction-document graphics: 45-degree hatch on hardscape, sand stipple on gravel, solid wall poche, canopies as thin double-ring outlines with center dot, black on white. Preserve layout. No text.",
        "P11 autumn": "Same plan in autumn: serviceberry copper-red, Hakone bronze-gold, deciduous warm mix, evergreens unchanged. Preserve layout, linework, and composition exactly. No text.",
        "P12 dusk lighting": "Dusk lighting-plan mood: deep blue-gray wash, warm glow pools at path lights and house openings, canopy silhouettes. Preserve layout exactly. No text.",
    }
    gen_preset = mo.ui.dropdown(options=list(PROMPT_PRESETS), value="— custom —", label="preset")
    gen_prompt = mo.ui.text_area(
        value="Refine this landscape plan, watercolor and ink presentation style, "
              "MARPA Front Range palette, no text or labels.",
        label="prompt", rows=5, full_width=True)
    gen_n = mo.ui.slider(1, 4, value=1, label="images")
    gen_res = mo.ui.dropdown(options=["1K", "2K", "4K"], value="2K", label="resolution")
    gen_go = mo.ui.run_button(label="⟳ GENERATE")
    mo.vstack([mo.md("## 1 · IMAGE GEN — model-switchable, regenerate at will"),
               mo.hstack([gen_model, gen_preset, gen_res, gen_n, gen_go]), gen_prompt])
    return IMG_MODELS, PROMPT_PRESETS, gen_model, gen_preset, gen_prompt, gen_n, gen_res, gen_go


@app.cell
def __(mo, gen_go, gen_model, gen_preset, PROMPT_PRESETS, gen_prompt, gen_n, gen_res, SRC, FAL_KEY,
       fal_sync, save_result_image, log_artifact, data_uri, time, FULL):
    _out = mo.md("*press GENERATE*")
    if gen_go.value and SRC and FAL_KEY:
        try:
            _p_text = PROMPT_PRESETS.get(gen_preset.value) or gen_prompt.value
            _payload = {"prompt": _p_text, "image_urls": [data_uri(SRC)],
                        "num_images": gen_n.value, "output_format": "png", "sync_mode": True}
            if "nano-banana-pro" in gen_model.value:
                _payload["resolution"] = gen_res.value
            _resp = fal_sync(gen_model.value, _payload)
            _paths = save_result_image(_resp, f"gen_{int(time.time())}")
            for _p in _paths:
                log_artifact("image", _p, {"model": gen_model.value, "prompt": _p_text})
            _out = mo.hstack([mo.Html(f'<img src="{data_uri(p)}" '
                                      f'style="max-height:78vh;max-width:48vw;border:1px solid #ccc"/>')
                              for p in _paths])
        except Exception as e:
            _out = mo.md(f"**error:** `{e}`")
    elif not FAL_KEY:
        _out = mo.md("**FAL_KEY not set** — `export FAL_KEY=...` and restart")
    mo.Html(f'<div style="{FULL}">') and mo.vstack([_out])
    return


@app.cell
def __(mo):
    # ---------- STATION 2 · FILTER BENCH controls ----------
    FILTERS = ["lineart (fal ControlNet)", "teed (fal)", "hed (fal)", "scribble (fal)",
               "depth-anything-v2 (fal)", "sam2 auto-segment (fal)",
               "canny (local)", "posterize (local)", "kmeans palette (local)",
               "bilateral paint (local)", "pencil sketch (local)", "stylization (local)",
               "skeleton/centerline (local)", "adaptive ink (local)"]
    flt_pick = mo.ui.dropdown(options=FILTERS, value="lineart (fal ControlNet)", label="filter")
    flt_a = mo.ui.slider(1, 255, value=60, label="param A (low thresh / levels / k)")
    flt_b = mo.ui.slider(1, 255, value=160, label="param B (high thresh)")
    flt_go = mo.ui.run_button(label="⟳ APPLY FILTER")
    mo.vstack([mo.md("## 2 · FILTER BENCH — ControlNet preprocessors + OpenCV"),
               mo.hstack([flt_pick, flt_a, flt_b, flt_go])])
    return FILTERS, flt_pick, flt_a, flt_b, flt_go


@app.cell
def __(mo, flt_go, flt_pick, flt_a, flt_b, SRC, FAL_KEY, fal_sync,
       save_result_image, log_artifact, data_uri, np, Image, time, FULL):
    import cv2
    _out2 = mo.md("*press APPLY FILTER*")
    if flt_go.value and SRC:
        try:
            _name = flt_pick.value
            if "(fal" in _name:
                _slug = {"lineart": "fal-ai/image-preprocessors/lineart",
                         "teed": "fal-ai/image-preprocessors/teed",
                         "hed": "fal-ai/image-preprocessors/hed",
                         "scribble": "fal-ai/image-preprocessors/scribble",
                         "depth-anything-v2": "fal-ai/image-preprocessors/depth-anything/v2",
                         "sam2": "fal-ai/sam2/auto-segment"}[_name.split(" ")[0]]
                _resp = fal_sync(_slug, {"image_url": data_uri(SRC), "sync_mode": True})
                _paths = save_result_image(_resp, f"flt_{int(time.time())}")
                _res = _paths[0]
            else:
                _a = np.array(Image.open(SRC).convert("RGB"))
                if "canny" in _name:
                    _g = cv2.cvtColor(_a, cv2.COLOR_RGB2GRAY)
                    _e = cv2.Canny(cv2.bilateralFilter(_g, 9, 60, 60), flt_a.value, flt_b.value)
                    _a = 255 - cv2.cvtColor(_e, cv2.COLOR_GRAY2RGB)
                elif "posterize" in _name:
                    _lv = max(2, flt_a.value // 32)
                    _a = (_a // (256 // _lv) * (256 // _lv)).astype("uint8")
                elif "kmeans" in _name:
                    _k = max(3, flt_a.value // 24)
                    _z = _a.reshape(-1, 3).astype("float32")
                    _, _lab, _ctr = cv2.kmeans(_z, _k, None,
                        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0),
                        2, cv2.KMEANS_PP_CENTERS)
                    _a = _ctr.astype("uint8")[_lab.flatten()].reshape(_a.shape)
                elif "pencil" in _name:
                    _, _a2 = cv2.pencilSketch(_a, sigma_s=60, sigma_r=0.07, shade_factor=0.05)
                    _a = _a2
                elif "stylization" in _name:
                    _a = cv2.stylization(_a, sigma_s=60, sigma_r=0.45)
                elif "skeleton" in _name:
                    _g = cv2.cvtColor(_a, cv2.COLOR_RGB2GRAY)
                    _ink = (255 - cv2.adaptiveThreshold(_g, 255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9))
                    _sk = cv2.ximgproc.thinning(_ink) if hasattr(cv2, "ximgproc") else _ink
                    _a = 255 - cv2.cvtColor(_sk, cv2.COLOR_GRAY2RGB)
                elif "adaptive ink" in _name:
                    _g = cv2.cvtColor(_a, cv2.COLOR_RGB2GRAY)
                    _ink = cv2.adaptiveThreshold(_g, 255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9)
                    _a = cv2.cvtColor(_ink, cv2.COLOR_GRAY2RGB)
                else:  # bilateral paint
                    for _ in range(3):
                        _a = cv2.bilateralFilter(_a, 11, 70, 70)
                _res = SRC.parent / f"flt_{int(time.time())}.png"
                Image.fromarray(_a).save(_res)
            log_artifact("filter", _res, {"filter": flt_pick.value, "src": str(SRC)})
            _out2 = mo.hstack([
                mo.Html(f'<img src="{data_uri(SRC)}" style="max-height:76vh;max-width:44vw"/>'),
                mo.Html(f'<img src="{data_uri(_res)}" style="max-height:76vh;max-width:44vw;'
                        f'border:2px solid #333"/>')])
        except Exception as e:
            _out2 = mo.md(f"**error:** `{e}`")
    mo.Html(f'<div style="{FULL}">') and mo.vstack([_out2])
    return (cv2,)


@app.cell
def __(mo):
    # ---------- STATION 3 · VIDEO GEN controls ----------
    VID_MODELS = {
        "Kling 2.1 (image→video)": "fal-ai/kling-video/v2.1/standard/image-to-video",
        "WAN 2.2 (image→video)": "fal-ai/wan/v2.2-a14b/image-to-video",
        "Veo 3 Fast (image→video)": "fal-ai/veo3/fast/image-to-video",
    }
    vid_model = mo.ui.dropdown(options=VID_MODELS, value="Kling 2.1 (image→video)", label="model")
    vid_prompt = mo.ui.text_area(
        value="Slow cinematic aerial drift over this landscape plan, gentle parallax, "
              "soft afternoon light, subtle wind in the canopies.",
        label="motion prompt", rows=3, full_width=True)
    vid_go = mo.ui.run_button(label="⟳ RENDER VIDEO (queued, ~1-3 min)")
    mo.vstack([mo.md("## 3 · VIDEO GEN — image→video via fal queue"),
               mo.hstack([vid_model, vid_go]), vid_prompt])
    return VID_MODELS, vid_model, vid_prompt, vid_go


@app.cell
def __(mo, vid_go, vid_model, vid_prompt, SRC, FAL_KEY, fal_queue,
       log_artifact, data_uri, urllib, time, LAB, FULL):
    _out3 = mo.md("*press RENDER VIDEO*")
    if vid_go.value and SRC and FAL_KEY:
        try:
            _resp = fal_queue(vid_model.value,
                              {"prompt": vid_prompt.value, "image_url": data_uri(SRC)})
            _url = (_resp.get("video") or {}).get("url") or _resp["videos"][0]["url"]
            _p = LAB / f"vid_{int(time.time())}.mp4"
            _p.write_bytes(urllib.request.urlopen(_url, timeout=300).read())
            log_artifact("video", _p, {"model": vid_model.value, "prompt": vid_prompt.value})
            _out3 = mo.Html(f'<video controls autoplay loop muted style="max-height:78vh;'
                            f'max-width:96%" src="{data_uri(_p)}"></video>')
        except Exception as e:
            _out3 = mo.md(f"**error:** `{e}`")
    mo.Html(f'<div style="{FULL}text-align:center">') and mo.vstack([_out3])
    return


@app.cell
def __(mo, Path):
    # ---------- STATION 4 · GLB VIEWER ----------
    _roots = [Path("/Volumes/marpa-volume/_Marpa_GraftKit/graftkit/_marpa-projects"),
              Path(__file__).parent]
    _glbs = []
    for _r in _roots:
        if _r.exists():
            _glbs += list(_r.rglob("*.glb"))[:200]
    glb_pick = mo.ui.dropdown(
        options={f"{p.parent.name}/{p.name}": str(p) for p in _glbs} or {"(no .glb found)": ""},
        label="GLB asset")
    mo.vstack([mo.md("## 4 · GLB VIEWER — plant assets & exported models"), glb_pick])
    return (glb_pick,)


@app.cell
def __(mo, glb_pick, Path, data_uri, FULL):
    if glb_pick.value:
        _uri = data_uri(Path(glb_pick.value))
        _html = (f'<script type="module" src="https://ajax.googleapis.com/ajax/libs/'
                 f'model-viewer/3.5.0/model-viewer.min.js"></script>'
                 f'<model-viewer src="{_uri}" camera-controls auto-rotate shadow-intensity="1" '
                 f'style="width:100%;height:82vh;background:#F1EDE2"></model-viewer>')
        _v = mo.iframe(_html, height="84vh")
    else:
        _v = mo.md("*pick a GLB — Gannan plant assets, VW exports, anything*")
    mo.Html(f'<div style="{FULL}">') and _v
    return


@app.cell
def __(mo):
    # ---------- STATION 5 · GAUSSIAN SPLAT / POINT CLOUD ----------
    splat_url = mo.ui.text(label=".splat / .ply URL (or local server path)",
                           value="", full_width=True)
    mo.vstack([mo.md("## 5 · GAUSSIAN SPLAT — drone captures & site scans"), splat_url])
    return (splat_url,)


@app.cell
def __(mo, splat_url, FULL):
    if splat_url.value:
        _html = (f'<script src="https://cdn.jsdelivr.net/npm/'
                 f'@mkkellogg/gaussian-splats-3d@0.4.7/build/gaussian-splats-3d.umd.min.js"></script>'
                 f'<div id="s" style="width:100%;height:82vh"></div><script>'
                 f'const v=new GaussianSplats3D.Viewer({{rootElement:document.getElementById("s")}});'
                 f'v.addSplatScene("{splat_url.value}").then(()=>v.start());</script>')
        _s = mo.iframe(_html, height="84vh")
    else:
        _s = mo.md("*paste a splat URL — e.g. a drone capture processed through Polycam/Luma, "
                   "or serve one locally with `python -m http.server`*")
    mo.Html(f'<div style="{FULL}">') and _s
    return


@app.cell
def __(mo, np, FULL):
    # ---------- STATION 6 · DECK.GL POINT CLOUD ----------
    import pydeck as pdk
    _n = 4000
    _rng = np.random.default_rng(7)
    _pts = np.column_stack([
        _rng.uniform(-105.2723, -105.2703, _n),
        _rng.uniform(39.9998, 40.0018, _n),
        _rng.gamma(2, 3, _n)])
    _layer = pdk.Layer("PointCloudLayer",
        data=[{"position": [float(x), float(y), float(z)],
               "color": [90 + int(z * 6) % 120, 140, 90]} for x, y, z in _pts],
        get_position="position", get_color="color", point_size=2)
    _deck = pdk.Deck(layers=[_layer],
        initial_view_state=pdk.ViewState(latitude=40.0008, longitude=-105.2713,
                                         zoom=16.5, pitch=55),
        map_style=None)
    mo.vstack([mo.md("## 6 · DECK.GL — site point clouds, GIS, survey overlays "
                     "*(demo scatter over Boulder — feed it LAS/PLY exports)*"),
               mo.iframe(_deck.to_html(as_string=True), height="78vh")])
    return (pdk,)


@app.cell
def __(mo, ledger_rows, FULL):
    # ---------- STATION 7 · ARTIFACT LEDGER ----------
    _rows = ledger_rows()
    _tbl = (mo.ui.table([{"kind": r["kind"], "path": r["path"],
                          "model": r.get("model", r.get("filter", "")),
                          "prompt": (r.get("prompt", "") or "")[:80]}
                         for r in reversed(_rows[-200:])])
            if _rows else mo.md("*nothing generated yet*"))
    mo.vstack([mo.md(f"## 7 · LEDGER — every artifact, every model, every prompt "
                     f"({len(_rows)} records)"), _tbl])
    return


if __name__ == "__main__":
    app.run()
