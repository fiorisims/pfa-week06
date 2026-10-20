"""Color Script Studio - a Frutiger Aero GUI for palette_sheet.py.

    python palette_gui.py

Drop in any number of images (or a PSD), pick how many colors to pull from
each one, choose the layout (rows / columns / grid), the swatch shape, size and
gap, the background, a title, hex labels and gradient strips - then:

  * Build preview  - render the sheet to a PNG;
  * Save PNG As... - write it to disk;
  * Export .aco    - save the colors as a Photoshop swatch file
                     (Swatches panel menu > Load Swatches);
  * Send to Photoshop - rebuild the very same layout natively in Photoshop:
                     one editable layer per palette with exact fills, live hex
                     text labels and the gradient strips as image layers.

If a document named "Color Script" is already open it is replaced, so hitting
Send repeatedly updates that one document instead of piling up files. The look
is the same Frutiger Aero glass as Turnaround Studio (it reuses its widgets).

Cross-platform: the GUI and the PNG/`.aco` output run anywhere; sending to
Photoshop needs Windows or macOS.
"""

import threading
import time
from pathlib import Path

import pygame

import palette_sheet as ps
import turnaround_gui as tg
from turnaround_gui import Button, Checkbox, Slider

HERE = Path(__file__).resolve().parent
OUT = ps.OUT_DEFAULT
WINDOW = (1120, 820)
DOC_NAME = ps.DOC_NAME
LOADING_DELAY = 5.0
SPIN_SPEED = 4.0

font = tg.font
glass_panel = tg.glass_panel
text_shadow = tg.text_shadow
vgrad = tg.vgrad
rounded = tg.rounded
draw_backdrop = tg.draw_backdrop
title_bar = tg.title_bar

SKY_TOP = tg.SKY_TOP
WATER = tg.WATER
INK = tg.INK
INK_SOFT = tg.INK_SOFT
WHITE = tg.WHITE
AQUA = tg.AQUA
AQUA_DEEP = tg.AQUA_DEEP
GREEN = tg.GREEN
VIOLET = tg.VIOLET

BG_PRESETS = ((24, 30, 40), (255, 255, 255), (238, 240, 244),
              (18, 44, 62), (48, 32, 58))


class App:
    FILE_PANEL = pygame.Rect(36, 100, 400, 226)
    OPT_PANEL = pygame.Rect(36, 344, 400, 428)
    PREV_PANEL = pygame.Rect(464, 100, 620, 470)
    LIST_AREA = pygame.Rect(52, 148, 368, 132)
    TITLE_FIELD = pygame.Rect(150, 374, 270, 30)
    COUNT_SLIDER = pygame.Rect(52, 428, 300, 14)
    SIZE_SLIDER = pygame.Rect(52, 496, 160, 14)
    GAP_SLIDER = pygame.Rect(232, 496, 160, 14)
    COLS_SLIDER = pygame.Rect(52, 652, 250, 14)
    RED_SLIDER = pygame.Rect(52, 730, 96, 12)
    GRN_SLIDER = pygame.Rect(160, 730, 96, 12)
    BLU_SLIDER = pygame.Rect(268, 730, 96, 12)
    BG_PREVIEW = pygame.Rect(384, 718, 40, 44)
    PREVIEW_FRAME = pygame.Rect(482, 146, 584, 384)
    STATUS_PANEL = pygame.Rect(464, 700, 620, 64)

    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Color Script Studio")
        self.screen = pygame.display.set_mode(WINDOW)
        self.clock = pygame.time.Clock()
        self.t = 0.0

        self.paths = []
        self.selected = None
        self.count = 6
        self.combine = False           # one merged palette instead of per image
        self.size_px = 96
        self.gap_px = 16
        self.orientation = "horizontal"
        self.shape = "square"
        self.cols = 4
        self.labels = True
        self.gradients = True
        self.show_images = True
        self.bg = list(BG_PRESETS[0])
        self.title_text = ""
        self.title_focus = False
        self.more = False              # advanced options expanded?

        self.sheet = None
        self.spec = None
        self.preview = None
        self.status = "Add images to begin."
        self.status_ok = True

        self.offsets = {}              # id -> [dx, dy] (survives a rebuild)
        self.zoom = None               # None = fit the frame
        self.pan = [0.0, 0.0]
        self._pv_scale = 1.0
        self.drag = None               # {"id", "start", "base"}
        self.pan_drag = None           # {"start", "base"}
        self.hover = None

        self.busy = False
        self.task = None               # "build" / "send"
        self.thread = None
        self.result = None
        self.error = None
        self.pending = None            # "save" / "aco" / "send" after a build
        self.busy_start = 0.0
        self.busy_frame = None
        self.busy_label = None
        self.running = True

        self._build_widgets()

    # ------------------------------------------------------------------ #
    def _build_widgets(self):
        self.buttons = [
            Button((52, 288, 130, 32), "Add file...", self.pick_files,
                   base=AQUA, tfont=font(15, True)),
            Button((188, 288, 122, 32), "Remove", self.remove_selected,
                   base=(110, 140, 170), tfont=font(15, True)),
            Button((316, 288, 104, 32), "Clear all", self.clear_all,
                   base=(150, 155, 165), tfont=font(15, True)),
            Button((464, 590, 190, 42), "Save PNG As...", self.save_png,
                   base=GREEN, tfont=font(16, True)),
            Button((668, 590, 190, 42), "Build preview", self.build,
                   base=AQUA, tfont=font(16, True)),
            Button((872, 590, 190, 42), "Export .aco", self.export_aco,
                   base=(120, 170, 200), tfont=font(16, True)),
            Button((464, 642, 620, 46), "Send to Photoshop", self.send,
                   base=VIOLET, tfont=font(19, True)),
            Button((944, 112, 132, 28), "Reset layout", self.reset_layout,
                   base=(120, 170, 200), tfont=font(13, True)),
            Button((WINDOW[0] - 58, 18, 44, 44), "X", self.request_close,
                   base=(216, 64, 64), tfont=font(22, True), radius=22),
        ]
        self.buttons += [
            Button((52 + i * 118, 542, 110, 28), name,
                   (lambda o=o: self.set_orientation(o)),
                   selected=(lambda o=o: self.orientation == o),
                   tfont=font(14, True))
            for i, (o, name) in enumerate((("horizontal", "Rows"),
                                           ("vertical", "Columns"),
                                           ("grid", "Grid")))]
        self.more_button = Button(
            (316, 350, 108, 22), "More options", self.toggle_more,
            base=(120, 170, 200), tfont=font(12, True),
            selected=lambda: self.more)
        self.buttons.append(self.more_button)
        self.more_buttons = [
            Button((52 + i * 118, 598, 110, 28), name,
                   (lambda s=s: self.set_shape(s)),
                   selected=(lambda s=s: self.shape == s),
                   tfont=font(14, True))
            for i, (s, name) in enumerate((("square", "Square"),
                                           ("rounded", "Rounded"),
                                           ("circle", "Circle")))]

        self.count_slider = Slider(self.COUNT_SLIDER, lambda: self.count,
                                   self._set_count, 2, 16)
        self.size_slider = Slider(self.SIZE_SLIDER, lambda: self.size_px,
                                  self._set_size, 32, 200)
        self.gap_slider = Slider(self.GAP_SLIDER, lambda: self.gap_px,
                                 self._set_gap, 0, 48)
        self.cols_slider = Slider(self.COLS_SLIDER, lambda: self.cols,
                                  self._set_cols, 2, 8)
        self.red_slider = Slider(self.RED_SLIDER, lambda: self.bg[0],
                                 lambda v: self._set_bg(0, v), 0, 255)
        self.grn_slider = Slider(self.GRN_SLIDER, lambda: self.bg[1],
                                 lambda v: self._set_bg(1, v), 0, 255)
        self.blu_slider = Slider(self.BLU_SLIDER, lambda: self.bg[2],
                                 lambda v: self._set_bg(2, v), 0, 255)
        self.sliders = [self.count_slider, self.size_slider]
        self.more_sliders = [self.gap_slider, self.cols_slider,
                             self.red_slider, self.grn_slider, self.blu_slider]
        self.combine_check = Checkbox(
            (52, 447, 230, 26), "One palette for all images",
            checked_fn=lambda: self.combine, toggle_fn=self.toggle_combine,
            tfont=font(13, True))
        self.labels_check = Checkbox(
            (52, 676, 130, 26), "Hex labels",
            checked_fn=lambda: self.labels, toggle_fn=self.toggle_labels,
            tfont=font(13, True))
        self.grad_check = Checkbox(
            (192, 676, 122, 26), "Gradients",
            checked_fn=lambda: self.gradients, toggle_fn=self.toggle_gradients,
            tfont=font(13, True))
        self.images_check = Checkbox(
            (324, 676, 96, 26), "Images",
            checked_fn=lambda: self.show_images, toggle_fn=self.toggle_images,
            tfont=font(13, True))
        self.checks = [self.combine_check]
        self.more_checks = [self.labels_check, self.grad_check,
                            self.images_check]

    def request_close(self):
        self.running = False

    # ------------------------------------------------------------------ #
    # file handling
    # ------------------------------------------------------------------ #
    def pick_files(self):
        dlg = tg._tk_dialog()
        if dlg is None:
            self.status, self.status_ok = (
                "File dialog unavailable - tkinter is not installed.", False)
            return
        tk, filedialog = dlg
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:                                  # noqa: BLE001
            pass
        paths = filedialog.askopenfilenames(
            title="Choose images for the palette",
            filetypes=[("Images + Photoshop",
                        "*.png *.jpg *.jpeg *.bmp *.tga *.gif *.webp "
                        "*.psd *.psb"),
                       ("Images", "*.png *.jpg *.jpeg *.bmp *.tga *.gif *.webp"),
                       ("Photoshop", "*.psd *.psb"),
                       ("All files", "*.*")])
        root.destroy()
        if paths:
            self.add_files(paths)

    def add_files(self, paths):
        added = 0
        for p in paths:
            p = str(Path(p))
            if Path(p).suffix.lower() not in ps.ALL_EXTS:
                continue
            if p not in self.paths:
                self.paths.append(p)
                added += 1
        if added:
            self.selected = len(self.paths) - 1
            self.status = "Added %d image(s)." % added
            self.status_ok = True

    def remove_selected(self):
        if self.selected is None or not self.paths:
            return
        name = Path(self.paths.pop(self.selected)).name
        self.selected = len(self.paths) - 1 if self.paths else None
        self.status, self.status_ok = "Removed %s." % name, True

    def clear_all(self):
        self.paths = []
        self.selected = None
        self.status, self.status_ok = "Cleared. Add images to begin.", True

    # ------------------------------------------------------------------ #
    # options
    # ------------------------------------------------------------------ #
    def _set_count(self, v):
        self.count = max(2, min(16, int(round(v))))

    def _set_size(self, v):
        self.size_px = max(32, min(200, int(round(v))))

    def _set_gap(self, v):
        self.gap_px = max(0, min(48, int(round(v))))

    def _set_cols(self, v):
        self.cols = max(2, min(8, int(round(v))))

    def _set_bg(self, channel, v):
        self.bg[channel] = max(0, min(255, int(round(v))))

    def set_orientation(self, o):
        self.orientation = o

    def set_shape(self, s):
        self.shape = s

    def toggle_combine(self):
        self.combine = not self.combine

    def toggle_more(self):
        self.more = not self.more

    def toggle_labels(self):
        self.labels = not self.labels

    def toggle_gradients(self):
        self.gradients = not self.gradients

    def toggle_images(self):
        self.show_images = not self.show_images

    def options(self):
        return {
            "swatches": self.count, "shared": self.combine,
            "shape": self.shape, "orientation": self.orientation,
            "cols": self.cols, "swatch": self.size_px, "gap": self.gap_px,
            "labels": self.labels, "gradients": self.gradients,
            "captions": True, "bg": tuple(self.bg), "title": self.title_text,
            "dpi": 150, "doc_name": DOC_NAME,
            "show_images": self.show_images,
        }

    # ------------------------------------------------------------------ #
    # build / send tasks (one worker at a time, polled by the main loop)
    # ------------------------------------------------------------------ #
    def build(self, then=None):
        if self.busy:
            return False
        if not self.paths:
            self.status, self.status_ok = "Add at least one image first.", False
            return False
        self._begin_busy("Working...", then)
        paths = list(self.paths)
        opts = self.options()
        opts["offsets"] = {k: tuple(v) for k, v in self.offsets.items()}
        self.task = "build"
        self.thread = threading.Thread(target=self._build_worker,
                                       args=(paths, opts), daemon=True)
        self.thread.start()
        return True

    def _build_worker(self, paths, opts):
        try:
            self.result = ps.build_sheet(paths, **opts)
        except Exception as exc:                           # noqa: BLE001
            self.error = str(exc)

    def send(self):
        self.build(then="send")

    def save_png(self):
        self.build(then="save")

    def _begin_busy(self, label, then):
        self.busy = True
        self.pending = then
        self.result = None
        self.error = None
        self.busy_start = time.time()
        try:
            self.busy_frame = self.screen.copy()
        except Exception:                                  # noqa: BLE001
            self.busy_frame = None
        self.busy_label = font(15, True).render(label, True, WHITE)

    def _poll_task(self):
        if not self.busy or self.thread is None:
            return
        if self.thread.is_alive():
            return
        self.thread = None
        if self.task == "build":
            self._apply_build()
        else:
            self._finish_send()

    def _apply_build(self):
        self.busy = False
        if self.error is not None:
            self.status, self.status_ok = "Build failed: %s" % self.error, False
            self.pending = None
            return
        self.sheet, self.spec, palettes = self.result
        self.offsets = {it["id"]: [it["dx"], it["dy"]]
                        for it in ps.spec_items(self.spec)
                        if it["dx"] or it["dy"]}
        self.pan = [0.0, 0.0]
        self._make_preview()
        n = sum(len(c) for _l, c in palettes)
        moved = "  (%d item(s) moved)" % len(self.offsets) if self.offsets else ""
        self.status = ("Built %dx%d px - %d palette(s), %d swatches%s"
                       % (self.spec["w"], self.spec["h"], len(palettes), n,
                          moved))
        self.status_ok = True
        then, self.pending = self.pending, None
        if then == "save":
            self._do_save()
        elif then == "aco":
            self._do_export_aco()
        elif then == "send":
            self._start_send()

    def _start_send(self):
        if self.spec is None:
            return
        self._begin_busy("Sending to Photoshop...", None)
        self.task = "send"
        spec = self.spec
        self.thread = threading.Thread(target=self._send_worker, args=(spec,),
                                       daemon=True)
        self.thread.start()

    def _send_worker(self, spec):
        try:
            self.result = ps.send_to_photoshop(spec, DOC_NAME)
        except Exception as exc:                           # noqa: BLE001
            self.result = (False, "Photoshop error: %s" % exc)

    def _finish_send(self):
        self.busy = False
        ok, msg = self.result if self.result else (False,
                                                   self.error or "failed")
        self.status, self.status_ok = msg, ok

    def _make_preview(self):
        if self.sheet is None:
            self.preview = None
            self._pv_scale = 1.0
            return
        f = self.PREVIEW_FRAME
        sw, sh = self.sheet.get_size()
        if self.zoom:
            sc = self.zoom
        else:
            sc = min(f.width / float(sw), f.height / float(sh), 3.0)
        w, h = max(1, int(sw * sc)), max(1, int(sh * sc))
        cap = 3.0
        if w > f.width * cap or h > f.height * cap:
            k = min(f.width * cap / w, f.height * cap / h)
            w, h, sc = max(1, int(w * k)), max(1, int(h * k)), sc * k
        self._pv_scale = sc
        if (w, h) == (sw, sh):
            self.preview = self.sheet
        else:
            self.preview = pygame.transform.smoothscale(self.sheet, (w, h))

    # ------------------------------------------------------------------ #
    # preview view: pan, zoom and drag-the-items-around
    # ------------------------------------------------------------------ #
    def fit_scale(self):
        if self.sheet is None:
            return 1.0
        f = self.PREVIEW_FRAME
        sw, sh = self.sheet.get_size()
        return min(f.width / float(sw), f.height / float(sh), 3.0)

    def preview_origin(self):
        """Top-left of the scaled sheet inside the preview frame."""
        f = self.PREVIEW_FRAME
        sw, sh = self.sheet.get_size()
        return (f.centerx - sw * self._pv_scale / 2.0 + self.pan[0],
                f.centery - sh * self._pv_scale / 2.0 + self.pan[1])

    def sheet_pos(self, pos):
        """Screen point -> sheet pixels."""
        ox, oy = self.preview_origin()
        return ((pos[0] - ox) / self._pv_scale, (pos[1] - oy) / self._pv_scale)

    def screen_pos(self, pt):
        """Sheet pixels -> screen point."""
        ox, oy = self.preview_origin()
        return (ox + pt[0] * self._pv_scale, oy + pt[1] * self._pv_scale)

    def item_rect_on_screen(self, item):
        ox, oy = self.preview_origin()
        sc = self._pv_scale
        return pygame.Rect(int(ox + item["x"] * sc), int(oy + item["y"] * sc),
                           max(2, int(item["w"] * sc)),
                           max(2, int(item["h"] * sc)))

    def pick_item(self, pos):
        """The topmost movable item under a screen point (or None)."""
        if self.spec is None:
            return None
        px, py = self.sheet_pos(pos)
        pad = 6.0 / self._pv_scale
        hit = None
        for it in ps.spec_items(self.spec):      # later items are drawn on top
            if (it["x"] - pad <= px <= it["x"] + it["w"] + pad
                    and it["y"] - pad <= py <= it["y"] + it["h"] + pad):
                hit = it
        return hit

    def _clamp_pan(self):
        if self.sheet is None:
            self.pan = [0.0, 0.0]
            return
        f = self.PREVIEW_FRAME
        sw, sh = self.sheet.get_size()
        lim_x = max(0.0, (sw * self._pv_scale - f.width) / 2.0) + 40
        lim_y = max(0.0, (sh * self._pv_scale - f.height) / 2.0) + 40
        self.pan[0] = max(-lim_x, min(lim_x, self.pan[0]))
        self.pan[1] = max(-lim_y, min(lim_y, self.pan[1]))

    def _refresh_sheet(self):
        if self.spec is None:
            return
        self.sheet = ps.render_spec(self.spec)
        self._make_preview()

    def _zoom(self, factor, pos):
        if self.sheet is None:
            return
        keep = self.sheet_pos(pos)
        self.zoom = max(0.1, min(8.0, (self.zoom or self.fit_scale()) * factor))
        self._make_preview()
        cur = self.screen_pos(keep)
        self.pan[0] += pos[0] - cur[0]
        self.pan[1] += pos[1] - cur[1]
        self._clamp_pan()

    def reset_layout(self):
        self.offsets = {}
        self.pan = [0.0, 0.0]
        self.zoom = None
        if self.spec is not None:
            ps.clear_offsets(self.spec)
            self._refresh_sheet()
        self.status = "Layout reset to the planned positions."
        self.status_ok = True

    def _drag_item(self, pos):
        pt = self.sheet_pos(pos)
        dx = self.drag["base"][0] + pt[0] - self.drag["start"][0]
        dy = self.drag["base"][1] + pt[1] - self.drag["start"][1]
        if not ps.set_offset(self.spec, self.drag["id"], dx, dy):
            return
        self.offsets[self.drag["id"]] = [int(round(dx)), int(round(dy))]
        self._refresh_sheet()

    # ------------------------------------------------------------------ #
    # save / export / send actions
    # ------------------------------------------------------------------ #
    def save_to(self, path):
        if self.sheet is None:
            return
        pygame.image.save(self.sheet, str(path))
        self.status, self.status_ok = "Saved %s" % path, True

    def _do_save(self):
        if self.sheet is None:
            return
        dlg = tg._tk_dialog()
        if dlg is None:
            self.status, self.status_ok = (
                "Save dialog unavailable - tkinter is not installed.", False)
            return
        tk, filedialog = dlg
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:                                  # noqa: BLE001
            pass
        path = filedialog.asksaveasfilename(
            title="Save palette sheet", defaultextension=".png",
            initialfile=OUT.name, filetypes=[("PNG image", "*.png")])
        root.destroy()
        if path:
            self.save_to(path)

    def aco_entries(self):
        """``[(r, g, b, name), ...]`` for the current spec (testable core)."""
        entries = []
        if not self.spec:
            return entries
        for pal in self.spec["palettes"]:
            label = str(pal["label"])[:20]
            for i, sw in enumerate(pal["swatches"], 1):
                c = sw["color"]
                entries.append((c[0], c[1], c[2], "%s %d" % (label, i)))
        return entries

    def export_aco(self):
        if self.spec is None:
            if not self.build(then="aco"):
                self.status, self.status_ok = "Build first.", False
            return
        self._do_export_aco()

    def _do_export_aco(self):
        entries = self.aco_entries()
        if not entries:
            self.status, self.status_ok = "Nothing to export.", False
            return
        dlg = tg._tk_dialog()
        if dlg is None:
            self.status, self.status_ok = (
                "Save dialog unavailable - tkinter is not installed.", False)
            return
        tk, filedialog = dlg
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:                                  # noqa: BLE001
            pass
        path = filedialog.asksaveasfilename(
            title="Export color swatches", defaultextension=".aco",
            initialfile="color_script.aco", filetypes=[("Photoshop swatches",
                                                       "*.aco")])
        root.destroy()
        if not path:
            return
        ps.write_aco(entries, path)
        self.status, self.status_ok = (
            "Wrote %s - load it via Swatches panel > Load Swatches" % path,
            True)

    def send_now_results(self, ok, msg):
        self.status, self.status_ok = msg, ok

    # ------------------------------------------------------------------ #
    def list_row_rect(self, i):
        return pygame.Rect(self.LIST_AREA.x + 6, self.LIST_AREA.y + 6 + i * 30,
                           self.LIST_AREA.width - 12, 26)

    def handle(self, event):
        if event.type == pygame.QUIT:
            return False
        if self.busy:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False
            if self.title_focus:
                if event.key == pygame.K_BACKSPACE:
                    self.title_text = self.title_text[:-1]
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.title_focus = False
                elif event.unicode and event.unicode.isprintable():
                    if len(self.title_text) < 48:
                        self.title_text += event.unicode
                return True
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.build()
            return True
        if event.type == pygame.MOUSEWHEEL:
            pos = pygame.mouse.get_pos()
            if self.PREVIEW_FRAME.collidepoint(pos):
                self._zoom(1.15 ** event.y, pos)
            return True
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                          pygame.MOUSEMOTION):
            for s in self.sliders:
                s.handle(event)
            for c in self.checks:
                c.handle(event)
            if self.more:
                for s in self.more_sliders:
                    s.handle(event)
                for c in self.more_checks:
                    c.handle(event)
        if event.type == pygame.MOUSEMOTION:
            if self.drag is not None:
                self._drag_item(event.pos)
            elif self.pan_drag is not None:
                self.pan[0] = (self.pan_drag["base"][0]
                               + event.pos[0] - self.pan_drag["start"][0])
                self.pan[1] = (self.pan_drag["base"][1]
                               + event.pos[1] - self.pan_drag["start"][1])
                self._clamp_pan()
            else:
                self.hover = (self.pick_item(event.pos)
                              if self.PREVIEW_FRAME.collidepoint(event.pos)
                              else None)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.drag = None
            self.pan_drag = None
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._on_click(event.pos)
        for b in self.buttons:
            b.handle(event)
        if self.more:
            for b in self.more_buttons:
                b.handle(event)
        return True

    def _on_click(self, pos):
        if self.TITLE_FIELD.collidepoint(pos):
            self.title_focus = True
            return
        self.title_focus = False
        if self.PREVIEW_FRAME.collidepoint(pos):
            item = self.pick_item(pos)
            if item is not None:
                self.drag = {"id": item["id"], "start": self.sheet_pos(pos),
                             "base": ps.get_offset(self.spec, item["id"])}
                self.status = ("Moving the %s - drag it anywhere, "
                               "or Reset layout." % item["kind"])
                self.status_ok = True
            else:
                self.pan_drag = {"start": pos, "base": tuple(self.pan)}
            return
        area = self.LIST_AREA
        if area.collidepoint(pos):
            i = (pos[1] - (area.y + 6)) // 30
            if 0 <= i < len(self.paths):
                self.selected = int(i)
                self.status = "Selected %s." % Path(self.paths[int(i)]).name
                self.status_ok = True

    # ------------------------------------------------------------------ #
    def run(self):
        while self.running:
            dt = self.clock.tick(60) / 1000.0
            self.t += dt
            for event in pygame.event.get():
                if not self.handle(event):
                    self.running = False
            self._poll_task()
            if self.busy and self.busy_frame is not None:
                self.draw_busy()
            else:
                self.draw()
            pygame.display.flip()
        pygame.quit()

    # ------------------------------------------------------------------ #
    def draw(self):
        screen = self.screen
        draw_backdrop(screen, self.t)
        title_bar(screen, "Color Script Studio")

        self.draw_files()
        self.draw_options()
        self.draw_preview()
        self.draw_status()
        for b in self.buttons:
            b.draw(screen)
        if self.more:
            for b in self.more_buttons:
                b.draw(screen)

    def draw_files(self):
        p = self.FILE_PANEL
        self.screen.blit(glass_panel(p.size), p.topleft)
        text_shadow(self.screen, "Images", font(19, True), INK,
                    (p.x + 18, p.y + 14), sh=(255, 255, 255))
        self.screen.blit(font(12).render(
            "any number of images + PSD   (click a row to select)", True,
            INK_SOFT), (p.x + 96, p.y + 22))
        area = self.LIST_AREA
        self.screen.blit(rounded(area.size, 10, (255, 255, 255, 95)),
                         area.topleft)
        if not self.paths:
            msg = font(15).render("No images yet - click 'Add file...'", True,
                                  INK_SOFT)
            self.screen.blit(msg, msg.get_rect(center=area.center))
        max_rows = (area.height - 12) // 30
        for i, path in enumerate(self.paths[:max_rows]):
            row = self.list_row_rect(i)
            if i == self.selected:
                self.screen.blit(rounded(row.size, 8, (120, 210, 245, 225)),
                                 row.topleft)
            ext = Path(path).suffix.lower()
            tag, tcol = ("PS", VIOLET) if ext in ps.PSD_EXTS else ("IMG",
                                                                   AQUA_DEEP)
            img = font(12, True).render(tag, True, tcol)
            self.screen.blit(img, (row.x + 8, row.y + 6))
            name = Path(path).name
            maxw = row.width - 60
            if font(15).size(name)[0] > maxw:
                while name and font(15).size(name + "...")[0] > maxw:
                    name = name[:-1]
                name += "..."
            self.screen.blit(font(15).render(name, True, INK),
                             (row.x + 44, row.y + 4))
        if len(self.paths) > max_rows:
            self.screen.blit(font(12).render(
                "+%d more" % (len(self.paths) - max_rows), True, INK_SOFT),
                (area.x + 8, area.bottom - 18))

    def _opt_panel(self):
        h = 428 if self.more else 300
        return pygame.Rect(self.OPT_PANEL.x, self.OPT_PANEL.y,
                           self.OPT_PANEL.width, h)

    def draw_options(self):
        p = self._opt_panel()
        self.screen.blit(glass_panel(p.size), p.topleft)
        text_shadow(self.screen, "Options", font(19, True), INK,
                    (p.x + 18, p.y + 4), sh=(255, 255, 255))
        self.more_button.label = ("Fewer options" if self.more
                                  else "More options")
        lbl = font(13, True)
        self.screen.blit(lbl.render("Sheet title", True, INK_SOFT), (54, 381))

        fr = self.TITLE_FIELD
        self.screen.blit(rounded(fr.size, 12, (255, 255, 255, 155)), fr)
        border = (60, 150, 210, 255) if self.title_focus else (255, 255, 255, 200)
        pygame.draw.rect(self.screen, border, fr, width=2, border_radius=12)
        shown = self.title_text or "Type a title..."
        col = INK if self.title_text else (120, 140, 160)
        self.screen.blit(font(17).render(shown, True, col),
                         (fr.x + 12, fr.y + 8))
        if self.title_focus and int(self.t * 2) % 2 == 0:
            cx = fr.x + 12 + font(17).size(self.title_text)[0] + 1
            pygame.draw.line(self.screen, INK, (cx, fr.y + 8),
                             (cx, fr.bottom - 8), 2)

        self.screen.blit(lbl.render(
            "Total colors" if self.combine else "Colors per image",
            True, INK_SOFT), (52, 412))
        self.screen.blit(font(14, True).render("%d" % self.count, True, INK),
                         (362, 412))

        self.combine_check.draw(self.screen)

        self.screen.blit(lbl.render("Swatch size", True, INK_SOFT), (52, 480))
        self.screen.blit(font(14, True).render("%d px" % self.size_px, True,
                                               INK), (218, 490))

        self.screen.blit(lbl.render("Orientation", True, INK_SOFT), (52, 524))

        self.count_slider.draw(self.screen)
        self.size_slider.draw(self.screen)

        if not self.more:
            self.screen.blit(font(12).render(
                "Need swatch shape, gap, grid, background or display options?",
                True, INK_SOFT), (52, 596))
            return

        self.screen.blit(lbl.render("Gap", True, INK_SOFT), (300, 480))
        self.screen.blit(font(14, True).render("%d px" % self.gap_px, True,
                                               INK), (398, 490))

        self.screen.blit(lbl.render("Swatch shape", True, INK_SOFT), (52, 580))

        self.screen.blit(lbl.render("Grid columns", True, INK_SOFT), (52, 634))
        self.screen.blit(font(14, True).render("%d" % self.cols, True, INK),
                         (312, 634))
        self.screen.blit(font(11).render(
            "(grid orientation only)", True, INK_SOFT), (382, 638))

        self.screen.blit(lbl.render("Background", True, INK_SOFT), (52, 706))
        self.screen.blit(font(11).render("R", True, (176, 56, 56)), (52, 714))
        self.screen.blit(font(11).render("G", True, (60, 150, 90)), (268, 714))
        self.screen.blit(font(11).render("B", True, (60, 110, 200)), (160, 714))
        for s in self.more_sliders:
            s.draw(self.screen)
        self.labels_check.draw(self.screen)
        self.grad_check.draw(self.screen)
        self.images_check.draw(self.screen)
        bp = self.BG_PREVIEW
        self.screen.blit(rounded(bp.size, 8, tuple(self.bg) + (255,)), bp)
        pygame.draw.rect(self.screen, (255, 255, 255, 200), bp, width=2,
                         border_radius=8)
        self.screen.blit(font(11, True).render(ps.hex_color(tuple(self.bg)),
                                               True, INK),
                         (bp.x - 2, bp.bottom + 2))

    def draw_preview(self):
        p = self.PREV_PANEL
        self.screen.blit(glass_panel(p.size), p.topleft)
        text_shadow(self.screen, "Preview", font(19, True), INK,
                    (p.x + 18, p.y + 14), sh=(255, 255, 255))
        self.screen.blit(font(12).render(
            "the sheet rebuilt natively in Photoshop on Send", True, INK_SOFT),
            (p.x + 100, p.y + 20))
        fr = self.PREVIEW_FRAME
        self.screen.blit(rounded(fr.size, 10, (255, 255, 255, 185)),
                         fr.topleft)
        pygame.draw.rect(self.screen, (255, 255, 255, 220), fr, width=2,
                         border_radius=10)
        if self.preview:
            clip = self.screen.get_clip()
            self.screen.set_clip(fr)
            ox, oy = self.preview_origin()
            self.screen.blit(self.preview, (int(ox), int(oy)))
            self._draw_drag_highlight()
            self.screen.set_clip(clip)
            self._draw_zoom_badge(fr)
        else:
            msg = font(15).render("Build to see your color script", True,
                                  INK_SOFT)
            self.screen.blit(msg, msg.get_rect(center=fr.center))
        self.screen.blit(font(12).render(
            "drag an image, swatch, caption or strip to move it   |   "
            "wheel = zoom   |   drag the background = pan", True, INK_SOFT),
            (fr.x + 2, fr.bottom + 6))

    def _draw_drag_highlight(self):
        active = None
        if self.drag is not None:
            active = self.drag["id"]
        elif self.hover is not None:
            active = self.hover["id"]
        if active is None or self.spec is None:
            return
        for it in ps.spec_items(self.spec):
            if it["id"] == active:
                r = self.item_rect_on_screen(it)
                pygame.draw.rect(self.screen, AQUA_DEEP, r, width=2,
                                 border_radius=6)
                pygame.draw.rect(self.screen, WHITE, r.inflate(2, 2), width=1,
                                 border_radius=7)
                break

    def _draw_zoom_badge(self, fr):
        pct = int(round(self._pv_scale * 100))
        label = "%d%%%s" % (pct, " (fit)" if not self.zoom else "")
        img = font(12, True).render(label, True, WHITE)
        r = pygame.Rect(fr.x + 8, fr.y + 8, img.get_width() + 14,
                        img.get_height() + 6)
        self.screen.blit(rounded(r.size, 8, (20, 40, 60, 175)), r.topleft)
        self.screen.blit(img, (r.x + 7, r.y + 3))

    def draw_status(self):
        p = self.STATUS_PANEL
        self.screen.blit(glass_panel(p.size, radius=14), p.topleft)
        col = (30, 120, 70) if self.status_ok else (176, 56, 56)
        text = self.status
        img = font(14, True).render(text, True, col)
        while img.get_width() > p.width - 28 and len(text) > 4:
            text = text[:-1]
            img = font(14, True).render(text + "...", True, col)
        self.screen.blit(img, (p.x + 16, p.y + 22))

    def draw_busy(self):
        self.screen.blit(self.busy_frame, (0, 0))
        if time.time() - self.busy_start < LOADING_DELAY:
            return
        fr = self.PREVIEW_FRAME
        overlay = pygame.Surface(fr.size, pygame.SRCALPHA)
        overlay.fill((10, 28, 44, 165))
        self.screen.blit(overlay, fr.topleft)
        cx, cy = fr.center
        tg.draw_loading_spinner(self.screen, (cx, cy - 16), self.t * SPIN_SPEED)
        if self.busy_label is not None:
            self.screen.blit(self.busy_label,
                             self.busy_label.get_rect(center=(cx, cy + 40)))


def main():
    App().run()


if __name__ == "__main__":
    main()
