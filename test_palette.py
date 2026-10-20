"""Checks for palette_sheet.py (Color Script Palette Organizer core).

    python test_palette.py            headless + a live Photoshop round trip
    python test_palette.py --no-live  headless only

Names the Photoshop document "Color Script Test" and closes it again, so it is
safe to run next to a real "Color Script" document.
"""

import argparse
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

import palette_sheet as ps

CHECKS = []
FAILS = []
LIVE_DOC = "Color Script Test"


def check(cond, msg):
    CHECKS.append(msg)
    if not cond:
        FAILS.append(msg)
    print("%s  %s" % ("ok  " if cond else "FAIL", msg))


def close(a, b, tol=6):
    return abs(a - b) <= tol


def near(c, want, tol=12):
    return all(abs(int(c[i]) - want[i]) <= tol for i in range(3))


def make_red(path, size=48):
    s = pygame.Surface((size, size))
    s.fill((255, 0, 0))
    pygame.image.save(s, str(path))
    return path


def make_blue(path, size=48):
    s = pygame.Surface((size, size))
    s.fill((0, 0, 255))
    pygame.image.save(s, str(path))
    return path


def make_ramp(path, a=(255, 0, 0), b=(0, 0, 255), size=96):
    s = pygame.Surface((size, size))
    for x in range(size):
        k = x / float(size - 1)
        col = (int(a[0] + (b[0] - a[0]) * k), int(a[1] + (b[1] - a[1]) * k),
               int(a[2] + (b[2] - a[2]) * k))
        pygame.draw.line(s, col, (x, 0), (x, size - 1))
    pygame.image.save(s, str(path))
    return path


def make_alpha(path, size=48):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    s.fill((0, 0, 0, 0))
    pygame.draw.rect(s, (0, 255, 0, 255), (0, 0, size, size // 2))
    pygame.image.save(s, str(path))
    return path


# --------------------------------------------------------------------------- #
def test_extraction(tmp):
    img = pygame.Surface((64, 64))
    img.fill((200, 40, 90))
    cols = ps.dominant_colors(img, 4)
    check(len(cols) == 1 and near(cols[0], (200, 40, 90)),
          "solid-color image -> one exact dominant color")

    ramp = pygame.image.load(str(make_ramp(tmp / "ramp.png")))
    cols = ps.dominant_colors(ramp, 6)
    check(2 <= len(cols) <= 6, "ramp image -> a handful of colors (%d)" % len(cols))
    check(any(near(c, (255, 0, 0), 40) for c in cols),
          "ramp palette contains the red end")
    check(any(near(c, (0, 0, 255), 40) for c in cols),
          "ramp palette contains the blue end")
    check(ps.dominant_colors(ramp, 6) == cols, "extraction is deterministic")

    alpha = pygame.image.load(str(make_alpha(tmp / "alpha.png")))
    cols = ps.dominant_colors(alpha, 4)
    check(len(cols) == 1 and near(cols[0], (0, 255, 0)),
          "fully transparent pixels are ignored")

    check(ps.dominant_colors(pygame.Surface((0, 0)), 3) == [],
          "empty image -> no colors")


def test_helpers():
    check(ps.hex_color((12, 160, 220)) == "#0CA0DC", "hex_color")
    try:
        check(ps.parse_color("#0CA0DC") == (12, 160, 220), "parse_color #RRGGBB")
        check(ps.parse_color("12,160,220") == (12, 160, 220), "parse_color r,g,b")
    except ValueError:
        check(False, "parse_color")
    check(ps.contrast_ink((250, 250, 250)) == ps.INK_DARK,
          "light swatch -> dark text")
    check(ps.contrast_ink((10, 10, 10)) == ps.INK_LIGHT,
          "dark swatch -> light text")

    r = ps.rect_pts(10, 20, 30, 40)
    check(r == [(10, 20), (40, 20), (40, 60), (10, 60)], "rect_pts corners")
    c = ps.circle_pts(0, 0, 100, 50)
    check(len(c) == 48 and all(0 <= x <= 100 and 0 <= y <= 50 for x, y in c),
          "circle_pts stay inside the box")
    k = ps.rounded_pts(0, 0, 100, 100)
    check(len(k) == 28 and min(x for x, _y in k) >= 0
          and max(x for x, _y in k) <= 100, "rounded_pts (4 corners x 7)")
    check(ps.shape_pts("square", 0, 0, 10, 10) == r[:4] or
          len(ps.shape_pts("square", 0, 0, 10, 10)) == 4,
          "shape_pts square")

    strip = ps.gradient_strip([(255, 0, 0), (0, 0, 255)], 64, 8)
    check(strip.get_size() == (64, 8), "gradient strip size")
    check(near(strip.get_at((0, 4))[:3], (255, 0, 0), 2),
          "gradient starts at the first color")
    check(near(strip.get_at((63, 4))[:3], (0, 0, 255), 2),
          "gradient ends at the last color")
    single = ps.gradient_strip([(9, 9, 9)], 16, 4)
    check(near(single.get_at((8, 2))[:3], (9, 9, 9)), "single-color strip")


def test_layout():
    pal = [("one", [(10, 10, 10), (200, 0, 0), (0, 0, 200)]),
           ("two", [(0, 200, 0), (0, 0, 0)])]
    spec = ps.plan_layout(pal, shape="square", orientation="horizontal",
                          swatch=100, gap=20, labels=True, gradients=True,
                          bg=(255, 255, 255), title="Script")
    check(spec["w"] > 3 * 100 and spec["h"] > 2 * 100,
          "horizontal sheet is big enough for the swatches")
    p0, p1 = spec["palettes"]
    xs = [s["x"] for s in p0["swatches"]]
    check(xs == sorted(xs) and close(xs[1] - xs[0], 120),
          "horizontal palette lays swatches left to right")
    check(p1["swatches"][0]["y"] > p0["swatches"][0]["y"] + 100,
          "second palette sits below the first")
    check(p0["swatches"][0]["label_y"] > p0["swatches"][0]["y"] + 100,
          "hex label sits under its swatch")
    check(p0["strip"]["y"] > p0["swatches"][0]["label_y"],
          "gradient strip sits under the labels")
    check(p0["strip"]["w"] == 3 * 100 + 2 * 20, "strip spans the swatch row")
    check(spec["title"] is not None and spec["title"]["cx"] == spec["w"] / 2.0,
          "title is centred")

    grid = ps.plan_layout(pal, orientation="grid", cols=2, swatch=50, gap=10)
    g0 = grid["palettes"][0]["swatches"]
    check(g0[0]["x"] == g0[1]["x"] - 60, "grid: two swatches per row")
    check(g0[2]["y"] == g0[0]["y"] + 60 and g0[2]["x"] == g0[0]["x"],
          "grid: third swatch wraps to the next row")

    vert = ps.plan_layout(pal, orientation="vertical", swatch=50, gap=10)
    v0 = vert["palettes"][0]["swatches"]
    check(v0[1]["y"] == v0[0]["y"] + 60 and v0[1]["x"] == v0[0]["x"],
          "vertical: swatches stack downward")
    check(vert["palettes"][1]["swatches"][0]["x"] > v0[0]["x"],
          "vertical: second palette sits to the right")
    check(vert["palettes"][0]["caption"] is not None,
          "captions are planned by default")

    plain = ps.plan_layout([("x", [(1, 2, 3)])], labels=False, gradients=False,
                           captions=False)
    s = plain["palettes"][0]["swatches"][0]
    check("label_cx" not in s and plain["palettes"][0]["strip"] is None
          and plain["palettes"][0]["caption"] is None,
          "labels / gradients / captions can be turned off")

    try:
        ps.plan_layout([])
        check(False, "empty palette list raises")
    except ValueError:
        check(True, "empty palette list raises")

    # source images sit above the swatches
    img = pygame.Surface((120, 60))
    img.fill((10, 20, 30))
    with_img = ps.plan_layout([("one", [(1, 2, 3), (4, 5, 6)])], swatch=100,
                              gap=20, images=[[(img, "one")]])
    im = with_img["palettes"][0]["images"][0]
    check(abs(im["w"] / float(im["h"]) - 2.0) < 0.05 and im["h"] <= 100,
          "image thumbnail keeps its aspect ratio (got %dx%d)"
          % (im["w"], im["h"]))
    check(with_img["palettes"][0]["swatches"][0]["y"] > im["y"] + im["h"],
          "swatches sit below the image")
    no_img = ps.plan_layout([("one", [(1, 2, 3), (4, 5, 6)])], swatch=100,
                            gap=20)
    check(no_img["palettes"][0]["images"] == []
          and no_img["h"] < with_img["h"],
          "images can be turned off (and make the sheet shorter)")
    check(im["id"] == "img:0:0" and
          with_img["palettes"][0]["swatches"][0]["id"] == "sw:0:0",
          "planned elements get stable ids")


def test_items(tmp):
    red = make_red(tmp / "it_red.png", 40)
    _surf, spec, _pal = ps.build_sheet([str(red)], swatches=3, swatch=60,
                                       gap=20, bg=(255, 255, 255))
    kinds = {it["kind"] for it in ps.spec_items(spec)}
    check({"swatch", "image", "strip", "caption"} <= kinds,
          "spec_items lists every movable element")

    sw = next(it for it in ps.spec_items(spec) if it["kind"] == "swatch")
    el = sw["el"]
    old = (int(el["x"] + el["w"] / 2), int(el["y"] + el["h"] / 2))
    ps.set_offset(spec, sw["id"], 40, 30)
    moved = next(it for it in ps.spec_items(spec) if it["id"] == sw["id"])
    check(moved["x"] == sw["x"] + 40 and moved["y"] == sw["y"] + 30,
          "set_offset moves the item")
    frame = ps.render_spec(spec)
    check(near(frame.get_at(old)[:3], (255, 255, 255)),
          "the old spot is empty after a move")
    new = (int(moved["x"] + moved["w"] / 2), int(moved["y"] + moved["h"] / 2))
    check(near(frame.get_at(new)[:3], (255, 0, 0)),
          "the item paints at its new spot")

    img = next(it for it in ps.spec_items(spec) if it["kind"] == "image")
    ps.set_offset(spec, img["id"], 0, -25)
    check(ps.get_offset(spec, img["id"]) == (0, -25)
          and Path(img["el"]["png"]).exists(),
          "images are draggable too (thumbnail PNG exists)")

    ps.clear_offsets(spec)
    check(ps.get_offset(spec, sw["id"]) == (0, 0)
          and ps.get_offset(spec, img["id"]) == (0, 0),
          "clear_offsets snaps everything back")

    jsx = ps.build_palette_jsx(spec)
    check('"dx"' in jsx and '"surf"' not in jsx,
          "JSX carries the offsets and never the raw surfaces")
    check("Image 1 -" in jsx, "JSX names the image layers")


def test_build(tmp):
    red = make_red(tmp / "red.png")
    blue = make_blue(tmp / "blue.png", 64)
    surf, spec, palettes = ps.build_sheet(
        [str(red), str(blue)], swatches=4, shape="square", swatch=64, gap=16,
        labels=True, gradients=True, bg=(255, 255, 255))
    check(len(palettes) == 2, "one palette per image")
    check(surf.get_size() == (spec["w"], spec["h"]),
          "rendered PNG matches the planned size")
    sw = spec["palettes"][0]["swatches"][0]
    got = surf.get_at((int(sw["x"] + sw["w"] / 2), int(sw["y"] + sw["h"] / 2)))
    check(near(got[:3], (255, 0, 0)), "first swatch renders its color")
    sw1 = spec["palettes"][1]["swatches"][0]
    got1 = surf.get_at((int(sw1["x"] + sw1["w"] / 2), int(sw1["y"] + sw1["h"] / 2)))
    check(near(got1[:3], (0, 0, 255)), "second palette renders its color")
    check(spec["palettes"][0]["strip"]["png"]
          and Path(spec["palettes"][0]["strip"]["png"]).exists(),
          "gradient strip PNGs are written")
    im = spec["palettes"][0]["images"][0]
    got_im = surf.get_at((int(im["x"] + im["w"] / 2),
                          int(im["y"] + im["h"] / 2)))
    check(near(got_im[:3], (255, 0, 0)),
          "the source image renders above the swatches")
    no_im, spec_no, _p = ps.build_sheet([str(red), str(blue)], swatches=4,
                                        swatch=64, gap=16, show_images=False)
    check(spec_no["h"] < spec["h"] and spec_no["palettes"][0]["images"] == [],
          "show_images=False drops the thumbnails")

    shared, spec_s, pal_s = ps.build_sheet(
        [str(red), str(blue)], swatches=2, shared=True, title="Mixed")
    check(len(pal_s) == 1 and len(pal_s[0][1]) >= 2,
          "shared mode merges into one palette")
    check(spec_s["title"]["text"] == "Mixed", "shared mode uses the title")
    check(len(spec_s["palettes"][0]["images"]) == 2,
          "shared mode shows every source image")
    check(not any("surf" in im for im in spec_s["palettes"][0]["images"]),
          "saved specs carry no raw surfaces")
    check(spec["palettes"][0]["images"][0]["png"]
          and Path(spec["palettes"][0]["images"][0]["png"]).exists(),
          "image thumbnails are written to disk")

    jsx = ps.build_palette_jsx(spec)
    check("var SPEC = {" in jsx and '"doc_name"' in jsx,
          "JSX payload embeds the spec")
    check("%s" not in jsx, "JSX template has no unresolved placeholders")
    check(jsx.count("{") == jsx.count("}") and jsx.count("[") == jsx.count("]"),
          "JSX payload has balanced braces/brackets")


def test_aco(tmp):
    path = tmp / "sw.aco"
    ps.write_aco([(12, 160, 220, "A"), (255, 0, 128, "Pink")], path)
    data = path.read_bytes()
    check(len(data) >= 2 + 10 + 2 + 10, "aco file has both blocks")
    ver, n = struct.unpack(">HH", data[:4])
    check(ver == 1 and n == 2, "aco v1 header")
    cid, r, g, b, pad = struct.unpack(">HHHHH", data[4:14])
    check(cid == 2 and r == 12 * 257 and g == 160 * 257 and b == 220 * 257
          and pad == 0, "aco v1 first record")
    off = 4 + 10 * 2
    ver2, n2 = struct.unpack(">HH", data[off:off + 4])
    check(ver2 == 2 and n2 == 2, "aco v2 header")
    cid2, r2, g2, b2 = struct.unpack(">HHHH", data[off + 4:off + 12])
    ln = struct.unpack(">I", data[off + 12:off + 16])[0]
    name = data[off + 16:off + 16 + ln]
    check(cid2 == 2 and r2 == 12 * 257 and name[0] == 1 and name[1:2] == b"A",
          "aco v2 name round-trips")

    ents = ps.aco_entries([("img", [(10, 20, 30), (200, 210, 220)])])
    check(ents == [(10, 20, 30, "img 1"), (200, 210, 220, "img 2")],
          "aco_entries from a palette list")
    spec_like = {"palettes": [{"label": "sky", "swatches": [
        {"id": "sw:0:0", "color": [1, 2, 3]},
        {"id": "sw:0:1", "color": [40, 50, 60]}]}]}
    check(ps.aco_entries(spec_like["palettes"])
          == [(1, 2, 3, "sky 1"), (40, 50, 60, "sky 2")],
          "aco_entries from a spec dict")
    p = ps.import_swatches(spec_like, tmp / "auto.aco")
    check(p.read_bytes()[2:4] == struct.pack(">H", 2),
          "import_swatches writes a 2-colour .aco")
    p2 = ps.import_swatches([("b", [(9, 8, 7)])], tmp / "list.aco")
    check(p2.exists(), "import_swatches accepts a palette list")
    try:
        ps.import_swatches([], tmp / "empty.aco")
        check(False, "import_swatches raises on an empty palette")
    except ValueError:
        check(True, "import_swatches raises on an empty palette")
    old_default = ps.ACO_DEFAULT
    ps.ACO_DEFAULT = tmp / "default.aco"
    try:
        p3 = ps.import_swatches(spec_like)
        check(p3 == tmp / "default.aco" and p3.exists(),
              "import_swatches defaults to ACO_DEFAULT")
    finally:
        ps.ACO_DEFAULT = old_default


def test_cli(tmp):
    red = make_red(tmp / "r.png")
    out = tmp / "sheet.png"
    rc = ps.main([str(red), "--out", str(out), "--swatches", "3",
                  "--aco", str(tmp / "c.aco"), "--bg", "18,32,48",
                  "--title", "CLI test"])
    check(rc == 0 and out.exists(), "CLI writes the sheet PNG")
    img = pygame.image.load(str(out))
    check(img.get_width() > 0 and (tmp / "c.aco").exists(),
          "CLI writes the .aco file")
    check(img.get_at((2, 2))[:3] == (24 - 6, 32, 48),
          "CLI background colour is applied")

    no = tmp / "sheet_no_images.png"
    ps.main([str(red), "--out", str(no), "--swatches", "3", "--bg", "18,32,48",
             "--title", "CLI test", "--no-images"])
    check(pygame.image.load(str(no)).get_height() < img.get_height(),
          "CLI --no-images leaves the thumbnails out")


# --------------------------------------------------------------------------- #
def test_live(tmp):
    """Round trip: build a sheet and read it back out of Photoshop."""
    try:
        import photoshop_bridge
    except Exception as exc:                                   # noqa: BLE001
        check(False, "photoshop_bridge import (%s)" % exc)
        return

    red = make_red(tmp / "live_red.png", 40)
    blue = make_blue(tmp / "live_blue.png", 40)
    _surf, spec, _pal = ps.build_sheet(
        [str(red), str(blue)], swatches=2, swatch=80, gap=24, shape="square",
        labels=True, gradients=True, bg=(255, 255, 255), title="Live test")

    try:
        aco_out = tmp / "live_auto.aco"
        ok, msg = ps.send_to_photoshop(spec, LIVE_DOC, aco_path=aco_out)
        check(ok and "color script:" in msg, "send_to_photoshop: %s" % msg)
        check(aco_out.exists() and "swatches:" in msg,
              "send auto-writes the .aco: %s" % msg)
        if not ok:
            return

        s = spec["palettes"][0]["swatches"][0]
        cx, cy = int(s["x"] + s["w"] / 2), int(s["y"] + s["h"] / 2)
        s2 = spec["palettes"][1]["swatches"][0]
        cx2, cy2 = int(s2["x"] + s2["w"] / 2), int(s2["y"] + s2["h"] / 2)
        query = (
            'app.displayDialogs = DialogModes.NO;'
            'var d = null;'
            'for (var i = 0; i < app.documents.length; i++) {'
            '  if (app.documents[i].name === "%s") d = app.documents[i]; }'
            'if (!d) { __result__ = "MISSING"; } else {'
            '  var a = d.colorSamplers.add([%d, %d]);'
            '  var b = d.colorSamplers.add([%d, %d]);'
            '  var names = [];'
            '  for (var j = 0; j < d.artLayers.length; j++) {'
            '    names.push(d.artLayers[j].name); }'
            '  __result__ = "C1=" + a.color.rgb.red + "," + a.color.rgb.green +'
            '    "," + a.color.rgb.blue + " C2=" + b.color.rgb.red + "," +'
            '    b.color.rgb.green + "," + b.color.rgb.blue + " LAYERS=" +'
            '    d.artLayers.length + " NAMES=" + names.join("|");'
            '  a.remove(); b.remove(); }' % (LIVE_DOC, cx, cy, cx2, cy2))
        out = photoshop_bridge.run(query)
        res = next((ln for ln in out.splitlines()
                    if ln.startswith("__result__")), out)
        check("C1=" in res, "live document is readable")
        c1 = res.split("C1=")[1].split(" ")[0].split(",")
        c2 = res.split("C2=")[1].split(" ")[0].split(",")
        check(near([float(v) for v in c1], (255, 0, 0), 8),
              "Photoshop swatch 1 holds the exact color (got %s)" % c1)
        check(near([float(v) for v in c2], (0, 0, 255), 8),
              "Photoshop swatch 2 holds the exact color (got %s)" % c2)
        check("LAYERS=" in res and int(res.split("LAYERS=")[1].split(" ")[0]) >= 4,
              "Photoshop doc has a layer per palette + gradients + labels")
        check("Gradient 1" in res and "Palette 1" in res,
              "layers are named after the palettes/gradients")
        check("Image 1 -" in res, "the source images are placed as layers")
    finally:
        try:
            cleanup = ('app.displayDialogs = DialogModes.NO;'
                       'var n = 0;'
                       'for (var i = app.documents.length - 1; i >= 0; i--) {'
                       '  if (app.documents[i].name === "%s") {'
                       '    app.documents[i].close(SaveOptions.DONOTSAVECHANGES);'
                       '    n++; } }'
                       '__result__ = "closed " + n;' % LIVE_DOC)
            photoshop_bridge.run(cleanup)
        except Exception:                                      # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
def test_gui(tmp):
    try:
        import palette_gui as pg
    except Exception as exc:                                   # noqa: BLE001
        check(False, "palette_gui import (%s)" % exc)
        return

    red = make_red(tmp / "g_red.png")
    blue = make_blue(tmp / "g_blue.png")
    app = pg.App()
    app.add_files([str(red), str(blue), str(tmp / "notes.txt")])
    check(len(app.paths) == 2, "GUI keeps only supported files")

    app.set_orientation("grid")
    app.set_shape("rounded")
    app.toggle_combine()
    app._set_count(5)
    app._set_size(72)
    app._set_gap(10)
    app._set_cols(3)
    opts = app.options()
    check(opts["shape"] == "rounded" and opts["shared"]
          and opts["orientation"] == "grid" and opts["swatch"] == 72,
          "GUI options update")

    check(app.build(), "GUI build starts")
    deadline = time.time() + 30
    while app.busy and time.time() < deadline:
        app._poll_task()
        time.sleep(0.01)
    check(not app.busy and app.sheet is not None,
          "GUI build finishes (%s)" % app.status)
    check(app.spec is not None and len(app.aco_entries()) >= 2,
          "GUI exposes the .aco entries")

    out = tmp / "g.png"
    app.save_to(out)
    check(out.exists(), "GUI save_to writes the PNG")

    app.title_focus = True
    for ch in "Demo":
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN,
                                             key=ord(ch.lower()), unicode=ch))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN,
                                         unicode="\r"))
    for e in pygame.event.get():
        app.handle(e)
    check(app.title_text == "Demo", "GUI title field types")
    app.build()
    deadline = time.time() + 30
    while app.busy and time.time() < deadline:
        app._poll_task()
        time.sleep(0.01)
    check(app.spec["title"] is not None
          and app.spec["title"]["text"] == "Demo",
          "GUI title lands on the sheet")

    check(app.options()["show_images"] is True
          and len(app.spec["palettes"][0]["images"]) >= 1,
          "GUI shows the source images by default")

    sw = next(it for it in ps.spec_items(app.spec) if it["kind"] == "swatch")
    r = app.item_rect_on_screen(sw)
    app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                  pos=r.center))
    check(app.drag is not None and app.drag["id"] == sw["id"],
          "GUI picks up a swatch to drag")
    app.handle(pygame.event.Event(pygame.MOUSEMOTION,
                                  pos=(r.centerx + 25, r.centery + 20)))
    app.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1,
                                  pos=(r.centerx + 25, r.centery + 20)))
    check(app.offsets.get(sw["id"]) not in (None, [0, 0]),
          "GUI records the moved item")
    check(ps.get_offset(app.spec, sw["id"]) != (0, 0),
          "GUI spec carries the new position")
    check(app.sheet is not None, "GUI re-renders after a move")

    app.build()
    deadline = time.time() + 30
    while app.busy and time.time() < deadline:
        app._poll_task()
        time.sleep(0.01)
    check(ps.get_offset(app.spec, sw["id"]) != (0, 0),
          "GUI keeps the moves across a rebuild")

    app.reset_layout()
    check(app.offsets == {} and ps.get_offset(app.spec, sw["id"]) == (0, 0),
          "GUI reset_layout clears every move")
    app._zoom(1.5, app.PREVIEW_FRAME.center)
    check(app.zoom is not None, "GUI zooms the preview")

    check(app.more is False, "GUI hides the advanced options by default")

    def click(rect):
        app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                      pos=rect.center))
        app.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1,
                                      pos=rect.center))

    shape_btn = app.more_buttons[0]                 # the "Square" button
    before = app.shape
    click(shape_btn.rect)
    check(app.shape == before,
          "advanced widgets are inert while the options are collapsed")

    app._set_gap(10)
    app.draw()
    click(app.more_button.rect)
    check(app.more is True, "the More options button expands the panel")
    click(shape_btn.rect)
    check(app.shape == "square", "advanced widgets work once expanded")
    check(app.options()["gap"] == 10,
          "expanded options still feed build_sheet")
    app.draw()
    click(app.more_button.rect)
    check(app.more is False and app.shape == "square",
          "collapsing keeps the chosen values")

    app.draw()
    app.draw_status()
    check(True, "GUI draw() runs without a display")
    app.remove_selected()
    app.clear_all()
    check(app.paths == [], "GUI remove / clear all")
    pygame.display.quit()


# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-live", action="store_true",
                    help="skip the live Photoshop round trip")
    a = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pygame.init()
    ps._fonts.clear()

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        test_extraction(tmp)
        test_helpers()
        test_layout()
        test_items(tmp)
        test_build(tmp)
        test_aco(tmp)
        test_cli(tmp)
        test_gui(tmp)

    if not a.no_live:
        with tempfile.TemporaryDirectory() as td:
            test_live(Path(td))
    else:
        print("skip  live Photoshop round trip (--no-live)")

    print()
    if FAILS:
        print("%d/%d checks FAILED:" % (len(FAILS), len(CHECKS)))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("all checks passed (%d)" % len(CHECKS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
