"""Local strip checks used during generate retries (layout, frame diversity)."""

from __future__ import annotations

from collections import deque
from io import BytesIO
from statistics import mean, median, pstdev

from PIL import Image, ImageFilter, ImageStat

FRAME_SLOTS = {
    "turnaround": 4,
    "idle": 5,
    "walk": 5,
    "dash": 5,
    "guard": 5,
    "hurt": 5,
    "jump": 5,
    "air_hurt": 5,
    "air_attack": 5,
    "attack": 5,
    "attack_up": 5,
    "attack_down": 5,
    "skill": 5,
    "combo_up": 5,
    "combo_down": 5,
    "combo": 5,
    "super": 5,
    "opening_cg": 5,
    "defeat_cg": 5,
    "win_cg": 5,
    "fx_skill": 4,
    "fx_combo_up": 4,
    "fx_combo_down": 4,
    "fx_super": 4,
    "happy": 5,
    "sad": 5,
    "sleep": 5,
    "wave": 5,
}

AIR_SLOTS = {"jump", "air_hurt", "air_attack", "attack_down", "combo_down"}
FALL_SLOTS = {"hurt", "air_hurt", "defeat_cg"}


def air_ground_lifts(feet_ys: list[int | None]) -> list[int]:
    """Pixels each frame's feet sit above the lowest (most grounded) feet in the set.

    Image Y grows downward, so lift = max(feet_y) - feet_y. Only valid when all
    feet_y share one canvas height (same strip row). Prefer air_lifts_from_cells
    when cells may have unequal heights.
    """
    valid = [int(y) for y in feet_ys if y is not None]
    if not valid:
        return [0 for _ in feet_ys]
    base = max(valid)
    out: list[int] = []
    for y in feet_ys:
        if y is None:
            out.append(0)
        else:
            out.append(max(0, base - int(y)))
    return out


def air_lifts_from_cells(cells: list[Image.Image]) -> list[int]:
    """Air lifts for possibly unequal cells: bottom-align onto a shared canvas first."""
    if not cells:
        return []
    abs_feet: list[int | None] = []
    max_h = max((c.size[1] for c in cells), default=0)
    for cell in cells:
        m = measure_cell_body(cell)
        if not m.get("body_h"):
            abs_feet.append(None)
            continue
        # Distance from feet to cell bottom → absolute Y if bottoms coincide.
        from_bottom = cell.size[1] - 1 - int(m["feet_y"])
        abs_feet.append(max_h - 1 - from_bottom)
    return air_ground_lifts(abs_feet)


def _is_bg(r: int, g: int, b: int, a: int) -> bool:
    if a < 16:
        return True
    mx, mn = max(r, g, b), min(r, g, b)
    sat = (mx - mn) / mx if mx else 0
    return g > 140 and b > 140 and r < 90 and sat > 0.35 and (g - r) > 40 and (b - r) > 40


def _open(png: bytes) -> Image.Image:
    im = Image.open(BytesIO(png)).convert("RGBA")
    w, h = im.size
    if w > 960:
        im = im.resize((960, max(1, round(h * 960 / w))), Image.Resampling.NEAREST)
    return im


def _fg_mask(im: Image.Image) -> list[list[bool]]:
    px = im.load()
    w, h = im.size
    return [[not _is_bg(*px[x, y]) for x in range(w)] for y in range(h)]


def _bbox(
    mask: list[list[bool]],
    x0: int,
    x1: int,
    y0: int | None = None,
    y1: int | None = None,
) -> tuple[int, int, int, int] | None:
    h = len(mask)
    y_start = 0 if y0 is None else max(0, y0)
    y_end = h if y1 is None else min(h, y1)
    minx, miny, maxx, maxy = x1, y_end, x0, y_start
    found = False
    for y in range(y_start, y_end):
        row = mask[y]
        for x in range(x0, x1):
            if row[x]:
                found = True
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
    if not found:
        return None
    return minx, miny, maxx, maxy


def _split_columns(mask: list[list[bool]], expected: int) -> list[tuple[int, int]]:
    h = len(mask)
    w = len(mask[0]) if h else 0
    if expected <= 1 or w < expected * 8:
        return [(0, w)]
    col_fg = [sum(1 for y in range(h) if mask[y][x]) for x in range(w)]
    thresh = max(2, int(h * 0.02))
    gutters: list[int] = []
    run = 0
    for x, n in enumerate(col_fg):
        if n <= thresh:
            run += 1
        else:
            if run >= max(3, w // (expected * 12)):
                gutters.append(x - run // 2)
            run = 0
    if len(gutters) >= expected - 1:
        cuts = [0] + gutters[: expected - 1] + [w]
        cuts = sorted(set(cuts))
        if len(cuts) == expected + 1:
            return [(cuts[i], cuts[i + 1]) for i in range(expected)]
    step = w / expected
    return [(int(i * step), int((i + 1) * step)) for i in range(expected)]


def _runs_above(values: list[int], thresh: int) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, n in enumerate(values):
        if n > thresh:
            if start is None:
                start = i
        elif start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(values)))
    return runs


def _merge_runs(runs: list[tuple[int, int]], max_gap: int) -> list[tuple[int, int]]:
    if not runs:
        return []
    out = [[runs[0][0], runs[0][1]]]
    for a, b in runs[1:]:
        if a - out[-1][1] <= max_gap:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _peak_columns(col_fg: list[int], expected: int) -> list[tuple[int, int]]:
    w = len(col_fg)
    expected = max(1, expected)
    if w < expected * 8:
        return [(0, w)]
    win = max(3, (w // (expected * 10)) | 1)
    smooth = []
    for i in range(w):
        a = max(0, i - win // 2)
        b = min(w, i + win // 2 + 1)
        smooth.append(sum(col_fg[a:b]) / (b - a))
    peak = max(smooth) if smooth else 0
    floor = peak * 0.16
    peaks: list[int] = []
    for i in range(2, w - 2):
        if smooth[i] < floor:
            continue
        if smooth[i] >= smooth[i - 1] and smooth[i] >= smooth[i + 1]:
            min_sep = max(8, w // (expected * 3))
            if not peaks or i - peaks[-1] > min_sep:
                peaks.append(i)
            elif smooth[i] > smooth[peaks[-1]]:
                peaks[-1] = i
    if len(peaks) > expected:
        peaks = sorted(sorted(peaks, key=lambda i: smooth[i], reverse=True)[:expected])
    if len(peaks) < 2:
        step = w / expected
        return [(int(i * step), int((i + 1) * step)) for i in range(expected)]
    cuts = [0]
    for i in range(len(peaks) - 1):
        lo, hi = peaks[i], peaks[i + 1]
        valley = min(range(lo, hi), key=lambda x: smooth[x])
        cuts.append(valley)
    cuts.append(w)
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]


def _merge_to_count(runs: list[tuple[int, int]], expected: int) -> list[tuple[int, int]]:
    groups = [[a, b] for a, b in runs]
    if not groups:
        return []
    expected = max(1, expected)
    while len(groups) > expected:
        best_i = 0
        best_gap = 10**9
        for i in range(len(groups) - 1):
            gap = groups[i + 1][0] - groups[i][1]
            if gap < best_gap:
                best_gap = gap
                best_i = i
        groups[best_i][1] = groups[best_i + 1][1]
        del groups[best_i + 1]
    return [(a, b) for a, b in groups]


def _equal_runs(width: int, expected: int) -> list[tuple[int, int]]:
    expected = max(1, expected)
    step = width / expected
    return [
        (int(round(i * step)), int(round(width if i == expected - 1 else (i + 1) * step)))
        for i in range(expected)
    ]


def _tile_cells(
    runs: list[tuple[int, int]],
    width: int,
    height: int,
    expected: int,
) -> list[dict]:
    if len(runs) != expected:
        runs = _equal_runs(width, expected)
    cells: list[dict] = []
    for i, (a, b) in enumerate(runs):
        left = 0 if i == 0 else (runs[i - 1][1] + a) // 2
        right = width if i == len(runs) - 1 else (b + runs[i + 1][0]) // 2
        if right - left < 2:
            right = min(width, left + max(2, width // expected))
        cells.append(
            {
                "x": left / width,
                "y": 0.0,
                "w": (right - left) / width,
                "h": 1.0,
                "px": {"x": left, "y": 0, "w": right - left, "h": height},
            }
        )
    return cells


def detect_strip_cells(im: Image.Image, expected: int = 6) -> dict:
    """Non-overlapping full-height tiles. Cuts sit in cyan gutters when possible."""
    rgba = im.convert("RGBA")
    mask = _fg_mask(rgba)
    height = len(mask)
    width = len(mask[0]) if height else 0
    expected = max(1, int(expected or 1))
    if width < 8 or height < 8:
        return {
            "cells": [{"x": 0, "y": 0, "w": 1, "h": 1, "px": {"x": 0, "y": 0, "w": width or 1, "h": height or 1}}],
            "rows": 1,
            "detected": 1,
            "expected": expected,
        }

    row_fg = [sum(1 for x in range(width) if mask[y][x]) for y in range(height)]
    bands = _merge_runs(_runs_above(row_fg, max(3, int(width * 0.015))), max_gap=max(4, height // 28))
    bands = [(a, b) for a, b in bands if b - a >= height * 0.12]
    if not bands:
        bands = [(0, height)]

    y0, y1 = bands[0] if len(bands) == 1 else (0, height)
    band_h = max(1, y1 - y0)
    col_fg = [sum(1 for y in range(y0, y1) if mask[y][x]) for x in range(width)]
    thresh = max(2, int(band_h * 0.03))
    runs = _merge_runs(_runs_above(col_fg, thresh), max_gap=max(2, width // 100))
    min_w = max(8, width // max(16, expected * 6))
    runs = [(a, b) for a, b in runs if b - a >= min_w]
    raw_n = len(runs)

    if len(bands) != 1:
        grid = detect_grid_2x2(rgba) if len(bands) >= 2 else None
        if grid:
            cells = []
            for panel in grid["panels"]:
                pw = max(1, int(panel["w"]))
                ph = max(1, int(panel["h"]))
                cells.append(
                    {
                        "x": int(panel["x"]) / width,
                        "y": int(panel["y"]) / height,
                        "w": pw / width,
                        "h": ph / height,
                        "px": {
                            "x": int(panel["x"]),
                            "y": int(panel["y"]),
                            "w": pw,
                            "h": ph,
                        },
                    }
                )
            return {
                "cells": cells,
                "rows": 2,
                "detected": 4,
                "expected": expected,
                "grid": "2x2",
                "runs": [],
            }
        cells = _tile_cells(_equal_runs(width, expected), width, height, expected)
        return {
            "cells": cells,
            "rows": len(bands),
            "detected": raw_n or len(cells),
            "expected": expected,
            "runs": [{"a": a, "b": b} for a, b in _equal_runs(width, expected)],
        }

    peak_runs = _peak_columns(col_fg, expected)
    if len(runs) > expected:
        runs = _merge_to_count(runs, expected)
    elif len(runs) < expected:
        runs = peak_runs if len(peak_runs) == expected else _equal_runs(width, expected)

    cells = _tile_cells(runs, width, height, expected)
    return {
        "cells": cells,
        "rows": 1,
        "detected": raw_n or len(cells),
        "expected": expected,
        "runs": [{"a": int(a), "b": int(b)} for a, b in runs],
    }


CYAN_FILL = (0, 255, 255, 255)


def is_key_cyan(r: int, g: int, b: int, a: int) -> bool:
    """True for chroma-key screen #00FFFF, teal leftovers, and cyan fringe — not gold/white/red FX."""
    if a < 12:
        return True
    if r >= 125:
        return False
    gb = min(g, b)
    if gb < 100:
        return False
    if gb <= r + 24:
        return False
    if abs(g - b) > 78:
        return False
    mx = max(r, g, b)
    mn = min(r, g, b)
    if mx and (mx - mn) / mx < 0.16:
        return False
    return True


def cyan_key_png(
    png_bytes: bytes,
    frames: int = 1,
    strict: bool = False,
    *,
    scrub: bool = True,
) -> bytes:
    """Flood-key #00FFFF (and fringe) to alpha 0. Used before writing game hero strips.

    scrub: erase model-drawn black/white comic gutters before keying. Disable for
    already-packed studio rebuilds (body-scale / unify) — scrub can punch holes
    through dark clothing belts and shatter feet measurement.
    """
    from collections import deque

    im = Image.open(BytesIO(png_bytes)).convert("RGBA")
    frames = max(1, int(frames or 1))
    if scrub and frames > 1:
        im = scrub_panel_borders(im, frames=frames)
    w, h = im.size
    pix = im.load()
    screen = [[is_key_cyan(*pix[x, y]) for x in range(w)] for y in range(h)]
    kill = [[False] * w for _ in range(h)]
    q: deque[tuple[int, int]] = deque()

    def seed(x: int, y: int) -> None:
        if not kill[y][x] and screen[y][x]:
            kill[y][x] = True
            q.append((x, y))

    for y in range(h):
        seed(0, y)
        seed(w - 1, y)
        for x in range(w):
            if pix[x, y][3] < 12:
                seed(x, y)
    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    fw = max(1, w // frames)
    for i in range(1, frames):
        gx = i * fw
        for y in range(h):
            for dx in range(-2, 3):
                xx = gx + dx
                if 0 <= xx < w:
                    seed(xx, y)

    while q:
        x, y = q.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and not kill[ny][nx] and screen[ny][nx]:
                kill[ny][nx] = True
                q.append((nx, ny))

    for y in range(h):
        for x in range(w):
            if kill[y][x]:
                r, g, b, a = pix[x, y]
                pix[x, y] = (r, g, b, 0)

    # Enclosed cyan islands (dust, foot specks) never touch the screen flood.
    for y in range(h):
        for x in range(w):
            r, g, b, a = pix[x, y]
            if a >= 12 and is_key_cyan(r, g, b, a):
                pix[x, y] = (r, g, b, 0)

    min_touch = 3 if strict else 4
    marked: list[tuple[int, int]] = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            r, g, b, a = pix[x, y]
            if a < 16:
                continue
            cyan = min(g, b) - r
            if cyan < (8 if strict else 18) or r >= (150 if strict else 130):
                continue
            t = 0
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
                if pix[x + dx, y + dy][3] < 16:
                    t += 1
            if t >= min_touch:
                marked.append((x, y))
    for x, y in marked:
        r, g, b, a = pix[x, y]
        pix[x, y] = (r, g, b, 0)

    for y in range(h):
        for x in range(w):
            r, g, b, a = pix[x, y]
            if a < 16:
                continue
            neigh = False
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and pix[nx, ny][3] < 16:
                    neigh = True
                    break
            if not neigh:
                continue
            cyan = min(g, b) - r
            if cyan <= (6 if strict else 12) or r >= (130 if strict else 110):
                continue
            factor = min(1.0, cyan / (120 if strict else 180))
            fade = 0.55 if strict else 0.35
            pix[x, y] = (
                r,
                max(0, int(g - cyan * (0.95 if strict else 0.85))),
                max(0, int(b - cyan * (0.95 if strict else 0.85))),
                int(a * (1 - fade * factor)),
            )

    out = BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


def cyan_key_image(
    im: Image.Image,
    frames: int = 1,
    strict: bool = False,
    *,
    scrub: bool = True,
) -> Image.Image:
    """Key a PIL image; returns a new RGBA image with cyan removed."""
    buf = BytesIO()
    im.convert("RGBA").save(buf, format="PNG")
    return Image.open(
        BytesIO(cyan_key_png(buf.getvalue(), frames=frames, strict=strict, scrub=scrub))
    ).convert("RGBA")


def _is_panel_ink(r: int, g: int, b: int, a: int = 255) -> bool:
    """Near-black / dark-gray ink used for model-drawn cell frames (not bright FX)."""
    if a < 10:
        return False
    # Pure-ish cyan must stay.
    if b >= 180 and g >= 180 and r <= 90:
        return False
    mx = max(r, g, b)
    if mx > 72:
        return False
    # Keep warm/dark orange embers that are part of fire (higher R relative).
    if r >= 55 and r > g + 18 and r > b + 18:
        return False
    return True


def _is_panel_white(r: int, g: int, b: int, a: int = 255) -> bool:
    """Near-white comic gutters (models sometimes stroke #FFF bars that survive cyan-key)."""
    if a < 10:
        return False
    if r < 210 or g < 210 or b < 210:
        return False
    return abs(r - g) <= 28 and abs(g - b) <= 28 and abs(r - b) <= 28


def scrub_panel_borders(im: Image.Image, frames: int = 1, fill: tuple[int, int, int, int] = CYAN_FILL) -> Image.Image:
    """Erase model-drawn black/white gutters / comic frames so cyan-key can remove them.

    Image models often stroke vertical bars between sprite cells; chroma-key only
    eats #00FFFF, so black or white bars survive into the game unless scrubbed first.
    """
    out = im.convert("RGBA").copy()
    w, h = out.size
    if w < 8 or h < 8:
        return out
    pix = out.load()
    frames = max(1, int(frames or 1))
    fw = max(1, w // frames)

    def is_gutter(r: int, g: int, b: int, a: int) -> bool:
        return _is_panel_ink(r, g, b, a) or _is_panel_white(r, g, b, a)

    def paint(x: int, y: int) -> None:
        r, g, b, a = pix[x, y]
        if is_gutter(r, g, b, a):
            pix[x, y] = fill

    # Outer comic frame (1–3 px).
    for t in range(3):
        for x in range(w):
            paint(x, t)
            paint(x, h - 1 - t)
        for y in range(h):
            paint(t, y)
            paint(w - 1 - t, y)

    # Vertical gutters at equal-width cuts (and a few px of slop).
    # CRITICAL: black outfits (Pol Pot etc.) often sit ON a cut — never wipe a
    # full dark clothing column into cyan (that becomes the mid-body “白条”).
    # Only erase ink that is already a thin bar sitting in a cyan field.
    def is_cyanish(r: int, g: int, b: int, a: int) -> bool:
        if a < 10:
            return True
        return b >= 160 and g >= 160 and r <= 100

    for i in range(1, frames):
        cx = i * fw
        for dx in range(-3, 4):
            x = cx + dx
            if not (0 <= x < w):
                continue
            body_core = 0
            gutter_between_cyan = 0
            for y in range(h):
                r, g, b, a = pix[x, y]
                if not is_gutter(r, g, b, a):
                    continue
                left = is_cyanish(*pix[x - 1, y]) if x > 0 else True
                right = is_cyanish(*pix[x + 1, y]) if x + 1 < w else True
                if left and right:
                    gutter_between_cyan += 1
                    continue
                # Dark pixel with dark neighbors = clothing interior, not a panel bar.
                dark_nb = 0
                for nx in (x - 1, x + 1):
                    if not (0 <= nx < w):
                        continue
                    nr, ng, nb, na = pix[nx, y]
                    if na >= 10 and _is_panel_ink(nr, ng, nb, na):
                        dark_nb += 1
                if dark_nb:
                    body_core += 1
            # Column runs through a torso/leg: only kill true cyan-flanked bar pixels.
            if body_core >= max(6, int(h * 0.06)):
                for y in range(h):
                    r, g, b, a = pix[x, y]
                    if not is_gutter(r, g, b, a):
                        continue
                    left = is_cyanish(*pix[x - 1, y]) if x > 0 else True
                    right = is_cyanish(*pix[x + 1, y]) if x + 1 < w else True
                    if left and right:
                        pix[x, y] = fill
                continue
            # Sparse / real gutter: require cyan on both sides, or white bar + one cyan side.
            if gutter_between_cyan >= max(4, int(h * 0.08)):
                for y in range(h):
                    r, g, b, a = pix[x, y]
                    if not is_gutter(r, g, b, a):
                        continue
                    left = is_cyanish(*pix[x - 1, y]) if x > 0 else True
                    right = is_cyanish(*pix[x + 1, y]) if x + 1 < w else True
                    if left and right:
                        pix[x, y] = fill
                    elif _is_panel_white(r, g, b, a) and (left or right):
                        pix[x, y] = fill
            else:
                for y in range(h):
                    r, g, b, a = pix[x, y]
                    if not is_gutter(r, g, b, a):
                        continue
                    left = is_cyanish(*pix[x - 1, y]) if x > 0 else True
                    right = is_cyanish(*pix[x + 1, y]) if x + 1 < w else True
                    if left and right:
                        pix[x, y] = fill

    # Full-width horizontal rule lines (comic gutters), NOT dark clothing belts.
    # A 1-row strip of dark suits has cyan *between cells* on every row. Counting
    # that as “40% cyan above/below this Y” used to paint the whole scanline —
    # punching a cyan hole through every waist (belt / navy jacket, mx≤72).
    # Only erase a pixel that itself sits in a cyan field (cyanish above AND below).
    for y in range(h):
        dark_n = sum(1 for x in range(w) if is_gutter(*pix[x, y]))
        if dark_n < max(8, int(w * 0.55)):
            continue
        above = sum(1 for x in range(w) if y > 0 and is_cyanish(*pix[x, y - 1]))
        below = sum(1 for x in range(w) if y + 1 < h and is_cyanish(*pix[x, y + 1]))
        if above < int(w * 0.40) or below < int(w * 0.40):
            continue
        for x in range(w):
            r, g, b, a = pix[x, y]
            if not is_gutter(r, g, b, a):
                continue
            up = y == 0 or is_cyanish(*pix[x, y - 1])
            dn = y + 1 >= h or is_cyanish(*pix[x, y + 1])
            if up and dn:
                pix[x, y] = fill

    # Intra-cell near-white bars (full-height columns / bottom rails) that sit inside a frame tile.
    # These are the “white box around jump pose” artifacts after cyan has already been keyed out.
    for i in range(frames):
        x0 = i * fw
        x1 = w if i == frames - 1 else (i + 1) * fw
        for x in range(x0, x1):
            white_n = sum(1 for y in range(h) if _is_panel_white(*pix[x, y]))
            if white_n >= max(8, int(h * 0.28)):
                for y in range(h):
                    if _is_panel_white(*pix[x, y]):
                        pix[x, y] = fill
        for y in range(max(0, h - 8), h):
            white_n = sum(1 for x in range(x0, x1) if _is_panel_white(*pix[x, y]))
            if white_n >= max(8, int((x1 - x0) * 0.22)):
                for x in range(x0, x1):
                    if _is_panel_white(*pix[x, y]):
                        pix[x, y] = fill

    return out


def _runs_from_layout(layout: dict, width: int, expected: int) -> list[tuple[int, int]]:
    raw = layout.get("runs") or []
    out: list[tuple[int, int]] = []
    for item in raw:
        if isinstance(item, dict):
            a, b = int(item.get("a") or 0), int(item.get("b") or 0)
        else:
            a, b = int(item[0]), int(item[1])
        if b > a:
            out.append((max(0, a), min(width, b)))
    if len(out) == expected:
        return out
    cells = layout.get("cells") or []
    out = []
    for cell in cells:
        px = cell.get("px") or {}
        x = int(px.get("x") or round(float(cell.get("x") or 0) * width))
        w = int(px.get("w") or round(float(cell.get("w") or 0) * width))
        if w > 1:
            out.append((max(0, x), min(width, x + w)))
    if len(out) == expected:
        return out
    return _equal_runs(width, expected)


def _run_index(runs: list[tuple[int, int]], x: int) -> int:
    for i, (a, b) in enumerate(runs):
        if a <= x < b:
            return i
    if not runs:
        return 0
    if x < runs[0][0]:
        return 0
    return len(runs) - 1


def _nearest_peak(peaks: list[int], x: int) -> int:
    best = 0
    best_d = 10**9
    for i, c in enumerate(peaks):
        d = abs(x - c)
        if d < best_d:
            best_d = d
            best = i
    return best


def _equal_peaks(width: int, expected: int) -> list[int]:
    expected = max(1, expected)
    return [int((i + 0.5) * width / expected) for i in range(expected)]


def _smooth_1d(values: list[int] | list[float], win: int) -> list[float]:
    width = len(values)
    win = max(1, win)
    out: list[float] = []
    for i in range(width):
        a = max(0, i - win)
        b = min(width, i + win + 1)
        out.append(sum(values[a:b]) / (b - a))
    return out


def _valley_ratio(smooth: list[float], a: int, b: int) -> float:
    lo, hi = (a, b) if a <= b else (b, a)
    if hi - lo < 2:
        return 1.0
    valley = min(smooth[lo:hi])
    return valley / max(smooth[a], smooth[b], 1e-6)


def _figure_peaks(col_fg: list[int], expected: int) -> list[int]:
    """One peak per standing person. Drop cape/flash satellites; keep two people whose capes touch."""
    width = len(col_fg)
    expected = max(1, expected)
    if width < expected * 8:
        return _equal_peaks(width, expected)
    win = max(5, (width // (expected * 10)) | 1)
    smooth = _smooth_1d(col_fg, win)
    peak_h = max(smooth) if smooth else 0
    floor = peak_h * 0.14
    min_keep = max(8, width // (expected * 4))
    cands: list[int] = []
    for i in range(2, width - 2):
        if smooth[i] < floor:
            continue
        if smooth[i] >= smooth[i - 1] and smooth[i] >= smooth[i + 1]:
            if not cands or i - cands[-1] > min_keep:
                cands.append(i)
            elif smooth[i] > smooth[cands[-1]]:
                cands[-1] = i
    if not cands:
        return _equal_peaks(width, expected)
    typical = width / expected
    while len(cands) > expected:
        sat_i = None
        sat_score = -1.0
        for i, p in enumerate(cands):
            others = [cands[j] for j in range(len(cands)) if j != i]
            if not others:
                continue
            nb = min(others, key=lambda q: abs(q - p))
            dist = abs(nb - p)
            rel = smooth[p] / max(smooth[nb], 1e-6)
            if dist < typical * 0.55 and rel < 0.64:
                score = (0.64 - rel) + (typical * 0.55 - dist) / typical
                if score > sat_score:
                    sat_score = score
                    sat_i = i
        if sat_i is not None:
            del cands[sat_i]
            continue
        best_j = None
        best_r = -1.0
        for j in range(len(cands) - 1):
            ratio = _valley_ratio(smooth, cands[j], cands[j + 1])
            if ratio > best_r:
                best_r = ratio
                best_j = j
        if best_j is not None and best_r >= 0.62:
            a, b = cands[best_j], cands[best_j + 1]
            cands[best_j] = a if smooth[a] >= smooth[b] else b
            del cands[best_j + 1]
            continue
        weak = min(range(len(cands)), key=lambda i: smooth[cands[i]])
        del cands[weak]
    return cands


def _place_figures(cxs: list[float], expected: int) -> list[int]:
    """Map k whole figures onto expected slots by X order. Never invent a cut through a body."""
    n = len(cxs)
    if n == 0:
        return []
    expected = max(1, expected)
    order = sorted(range(n), key=lambda i: cxs[i])
    slots = [0] * n
    if n <= expected:
        for rank, i in enumerate(order):
            slots[i] = rank
        return slots
    groups = [[i] for i in order]
    while len(groups) > expected:
        best = 0
        best_gap = 10**9
        for g in range(len(groups) - 1):
            gap = cxs[groups[g + 1][0]] - cxs[groups[g][-1]]
            if gap < best_gap:
                best_gap = gap
                best = g
        groups[best] = groups[best] + groups[best + 1]
        del groups[best + 1]
    for slot, group in enumerate(groups):
        for i in group:
            slots[i] = slot
    return slots


def _x_overlap_frac(a0: int, a1: int, b0: int, b1: int) -> float:
    ox = max(0, min(a1, b1) - max(a0, b0) + 1)
    wa = max(1, a1 - a0 + 1)
    wb = max(1, b1 - b0 + 1)
    return ox / min(wa, wb)


def _gutter_thresh(height: int, expected: int) -> int:
    return max(2, int(height * 0.025))


def _drop_hairlines(mask: list[list[bool]]) -> list[list[bool]]:
    """Clear a 1px ground line that would otherwise glue an entire row of figures."""
    height = len(mask)
    width = len(mask[0]) if height else 0
    out = [row[:] for row in mask]
    span_lim = max(8, width * 45 // 100)
    for y in range(height):
        xs = [x for x in range(width) if out[y][x]]
        if len(xs) < span_lim:
            continue
        above = sum(1 for x in range(width) if y and out[y - 1][x])
        below = sum(1 for x in range(width) if y + 1 < height and out[y + 1][x])
        if above < span_lim // 2 and below < span_lim // 2:
            for x in range(width):
                out[y][x] = False
    return out


def _core_ranges(col_fg: list[int], peaks: list[int], height: int) -> list[tuple[int, int]]:
    """Fat torso columns around each person. Thin guns/canes stay outside so they are not vertically sliced."""
    width = len(col_fg)
    thresh = max(10, int(height * 0.11))
    out: list[tuple[int, int]] = []
    for i, peak in enumerate(peaks):
        lo = 0 if i == 0 else (peaks[i - 1] + peak) // 2
        hi = width if i == len(peaks) - 1 else (peak + peaks[i + 1]) // 2
        a = peak
        while a > lo and col_fg[a - 1] >= thresh:
            a -= 1
        b = peak
        while b + 1 < hi and col_fg[b + 1] >= thresh:
            b += 1
        if b < a:
            a = b = peak
        out.append((a, b + 1))
    return out


def _flood_cc(mask: list[list[bool]], labels: list[list[int]], x0: int, y0: int, seen: list[list[bool]]) -> list[tuple[int, int]]:
    height = len(mask)
    width = len(mask[0]) if height else 0
    pixels: list[tuple[int, int]] = []
    q: deque[tuple[int, int]] = deque([(x0, y0)])
    seen[y0][x0] = True
    while q:
        x, y = q.popleft()
        pixels.append((x, y))
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and mask[ny][nx] and labels[ny][nx] < 0 and not seen[ny][nx]:
                seen[ny][nx] = True
                q.append((nx, ny))
    return pixels


def _label_extension(mask: list[list[bool]], labels: list[list[int]], pixels: list[tuple[int, int]], peaks: list[int]) -> None:
    """Give a leftover blob to the body it actually touches; if it touches two, watershed from the contacts."""
    height = len(mask)
    width = len(mask[0]) if height else 0
    contacts: dict[int, list[tuple[int, int]]] = {}
    for x, y in pixels:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                owner = labels[ny][nx]
                if owner >= 0:
                    contacts.setdefault(owner, []).append((x, y))
    if not contacts:
        sx = sum(x for x, _y in pixels) / len(pixels)
        owner = _nearest_peak(peaks, int(sx))
        for x, y in pixels:
            labels[y][x] = owner
        return
    if len(contacts) == 1:
        owner = next(iter(contacts))
        for x, y in pixels:
            labels[y][x] = owner
        return
    q: deque[tuple[int, int, int]] = deque()
    claimed: dict[tuple[int, int], int] = {}
    for owner, pts in contacts.items():
        for x, y in pts:
            if (x, y) in claimed:
                continue
            claimed[(x, y)] = owner
            labels[y][x] = owner
            q.append((x, y, owner))
    pixel_set = set(pixels)
    while q:
        x, y, owner = q.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (nx, ny) not in pixel_set or (nx, ny) in claimed:
                continue
            claimed[(nx, ny)] = owner
            labels[ny][nx] = owner
            q.append((nx, ny, owner))


def _attach_orphans(mask: list[list[bool]], labels: list[list[int]], peaks: list[int], hop: int = 8) -> None:
    """Jump a few cyan pixels so a detached flash/swoosh still follows its owner."""
    height = len(mask)
    width = len(mask[0]) if height else 0
    q: deque[tuple[int, int, int, int]] = deque()
    seen = [[-1] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if labels[y][x] >= 0:
                q.append((x, y, labels[y][x], 0))
                seen[y][x] = 0
    while q:
        x, y, owner, hops = q.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if mask[ny][nx]:
                if labels[ny][nx] >= 0:
                    continue
                labels[ny][nx] = owner
                if seen[ny][nx] < 0:
                    seen[ny][nx] = 0
                    q.append((nx, ny, owner, 0))
            elif hops < hop and seen[ny][nx] < 0:
                seen[ny][nx] = hops + 1
                q.append((nx, ny, owner, hops + 1))
    for y in range(height):
        for x in range(width):
            if mask[y][x] and labels[y][x] < 0:
                labels[y][x] = _nearest_peak(peaks, x)


def label_strip_figures(im: Image.Image, layout: dict) -> list[list[int]]:
    """Body cores first, then guns/canes/FX grow from the body they touch — not from the nearest X peak."""
    rgba = im.convert("RGBA")
    mask = _drop_hairlines(_fg_mask(rgba))
    height = len(mask)
    width = len(mask[0]) if height else 0
    expected = max(1, int(layout.get("expected") or len(layout.get("cells") or []) or 1))
    labels = [[-1] * width for _ in range(height)]
    if width < 2 or height < 2:
        return labels
    col_fg = [sum(1 for y in range(height) if mask[y][x]) for x in range(width)]
    peaks = _figure_peaks(col_fg, expected)
    if not peaks:
        return labels
    core_of = [-1] * width
    for i, (a, b) in enumerate(_core_ranges(col_fg, peaks, height)):
        for x in range(a, b):
            core_of[x] = i
    q: deque[tuple[int, int]] = deque()
    for i, peak in enumerate(peaks):
        x0 = min(width - 1, max(0, peak))
        for y in range(height):
            if mask[y][x0] and labels[y][x0] < 0 and core_of[x0] == i:
                labels[y][x0] = i
                q.append((x0, y))
        if not any(labels[y][x0] == i for y in range(height)):
            for dx in range(1, max(8, width // 40)):
                hit = False
                for x in (x0 - dx, x0 + dx):
                    if 0 <= x < width and core_of[x] == i:
                        for y in range(height):
                            if mask[y][x] and labels[y][x] < 0:
                                labels[y][x] = i
                                q.append((x, y))
                                hit = True
                if hit:
                    break
    while q:
        x, y = q.popleft()
        owner = labels[y][x]
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and mask[ny][nx] and labels[ny][nx] < 0 and core_of[nx] == owner:
                labels[ny][nx] = owner
                q.append((nx, ny))
    seen = [[False] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if mask[y][x] and labels[y][x] < 0 and not seen[y][x]:
                blob = _flood_cc(mask, labels, x, y, seen)
                if blob:
                    _label_extension(mask, labels, blob, peaks)
    _attach_orphans(mask, labels, peaks)
    return labels


def scrub_foreign_pixels(
    im: Image.Image,
    box: tuple[int, int, int, int],
    labels: list[list[int]],
    index: int,
) -> Image.Image:
    """Crop a cell and paint other figures' pixels cyan so neighboring bodies disappear."""
    left, top, right, bottom = box
    crop = im.crop((left, top, right, bottom)).convert("RGBA")
    if not labels:
        return crop
    px = crop.load()
    height = len(labels)
    width = len(labels[0]) if height else 0
    cw, ch = crop.size
    for ly in range(ch):
        gy = top + ly
        if gy < 0 or gy >= height:
            continue
        row = labels[gy]
        for lx in range(cw):
            gx = left + lx
            if gx < 0 or gx >= width:
                continue
            owner = row[gx]
            if owner >= 0 and owner != index:
                px[lx, ly] = CYAN_FILL
    return crop


def figure_bboxes(labels: list[list[int]], expected: int) -> list[tuple[int, int, int, int] | None]:
    height = len(labels)
    width = len(labels[0]) if height else 0
    boxes = [[width, height, -1, -1] for _ in range(expected)]
    for y in range(height):
        row = labels[y]
        for x in range(width):
            i = row[x]
            if 0 <= i < expected:
                if x < boxes[i][0]:
                    boxes[i][0] = x
                if y < boxes[i][1]:
                    boxes[i][1] = y
                if x > boxes[i][2]:
                    boxes[i][2] = x
                if y > boxes[i][3]:
                    boxes[i][3] = y
    out: list[tuple[int, int, int, int] | None] = []
    for minx, miny, maxx, maxy in boxes:
        if maxx < minx or maxy < miny:
            out.append(None)
        else:
            out.append((minx, miny, maxx + 1, maxy + 1))
    return out


SPLIT_VARIANT_COUNT = 6
SPLIT_VARIANT_LABELS = (
    "按人物轮廓装箱",
    "按格缝切开（少裁）",
    "等宽切开（保持原图）",
    "轮廓装箱·留边更多",
    "轮廓装箱·裁得更紧",
    "2×2 宫格→单行",
)


def detect_grid_2x2(im: Image.Image) -> dict | None:
    """Detect a 2×2 comic/CG contact sheet on cyan. Returns panel boxes in reading order or None."""
    rgba = im.convert("RGBA")
    mask = _fg_mask(rgba)
    height = len(mask)
    width = len(mask[0]) if height else 0
    if width < 32 or height < 32:
        return None
    row_fg = [sum(1 for x in range(width) if mask[y][x]) for y in range(height)]
    row_thresh = max(4, int(width * 0.04))
    bands = _merge_runs(_runs_above(row_fg, row_thresh), max_gap=max(3, height // 40))
    bands = [(a, b) for a, b in bands if b - a >= max(24, height // 8)]
    if len(bands) < 2:
        return None
    # 1-row 4-across (turnaround) with a thin waist hole looks like 2 bands × N
    # columns. That is not a 2×2 comic — refuse if the full sheet has 3+ figures.
    col_fg_all = [sum(1 for y in range(height) if mask[y][x]) for x in range(width)]
    col_runs = _merge_runs(
        _runs_above(col_fg_all, max(4, int(height * 0.08))),
        max_gap=max(2, width // 80),
    )
    col_runs = [(a, b) for a, b in col_runs if b - a >= max(16, width // 16)]
    if len(col_runs) >= 3:
        return None
    # Prefer the two strongest (tallest) bands
    bands = sorted(bands, key=lambda ab: ab[1] - ab[0], reverse=True)[:2]
    bands = sorted(bands, key=lambda ab: ab[0])
    panels: list[tuple[int, int, int, int]] = []
    for y0, y1 in bands:
        band_h = max(1, y1 - y0)
        col_fg = [sum(1 for y in range(y0, y1) if mask[y][x]) for x in range(width)]
        col_thresh = max(3, int(band_h * 0.06))
        runs = _merge_runs(_runs_above(col_fg, col_thresh), max_gap=max(2, width // 80))
        runs = [(a, b) for a, b in runs if b - a >= max(24, width // 8)]
        if len(runs) < 2:
            # Equal split this band
            mid = width // 2
            runs = [(0, mid), (mid, width)]
        elif len(runs) > 2:
            runs = _merge_to_count(runs, 2)
        for x0, x1 in runs[:2]:
            # Tighten to ink inside the tile
            minx, miny, maxx, maxy = x1, y1, x0, y0
            for y in range(y0, y1):
                row = mask[y]
                for x in range(x0, x1):
                    if not row[x]:
                        continue
                    if x < minx:
                        minx = x
                    if y < miny:
                        miny = y
                    if x > maxx:
                        maxx = x
                    if y > maxy:
                        maxy = y
            if maxx <= minx or maxy <= miny:
                panels.append((x0, y0, x1, y1))
            else:
                pad = max(2, min(8, (x1 - x0) // 40))
                panels.append(
                    (
                        max(0, minx - pad),
                        max(0, miny - pad),
                        min(width, maxx + 1 + pad),
                        min(height, maxy + 1 + pad),
                    )
                )
    if len(panels) != 4:
        return None
    # Reading order: top-left, top-right, bottom-left, bottom-right
    top = sorted(panels[:2], key=lambda p: p[0])
    bot = sorted(panels[2:], key=lambda p: p[0])
    ordered = top + bot
    return {
        "panels": [{"x": a, "y": b, "w": c - a, "h": d - b} for a, b, c, d in ordered],
        "rows": 2,
        "detected": 4,
        "expected": 4,
        "grid": "2x2",
    }


def looks_like_grid_2x2(im: Image.Image) -> bool:
    return detect_grid_2x2(im) is not None


def pack_grid_2x2(
    im: Image.Image,
    variant: int = 5,
) -> tuple[Image.Image, list[Image.Image], dict]:
    """Unpack a 2×2 cyan contact sheet into one horizontal 4-frame strip."""
    src = im.convert("RGBA")
    info = detect_grid_2x2(src)
    if not info:
        raise ValueError("看不出 2×2 宫格。请确认青底上有上下两排、每排两格画面。")
    crops: list[Image.Image] = []
    boxes: list[dict] = []
    for panel in info["panels"]:
        x0 = int(panel["x"])
        y0 = int(panel["y"])
        x1 = x0 + int(panel["w"])
        y1 = y0 + int(panel["h"])
        crops.append(src.crop((x0, y0, x1, y1)))
        boxes.append({"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})
    layout = {
        "cells": [],
        "rows": 2,
        "detected": 4,
        "expected": 4,
        "grid": "2x2",
        "runs": [],
    }
    sheet, frames, meta = _stack_frame_crops(
        crops,
        4,
        layout,
        variant,
        extra_pad=True,
        pad_ratio=28,
        src_boxes=boxes,
    )
    meta["variant_label"] = SPLIT_VARIANT_LABELS[5]
    meta["variant"] = 5
    meta["grid"] = "2x2"
    meta["rows"] = 1  # output is a single row
    meta["detected"] = 4
    return sheet, frames, meta


def _stack_frame_crops(
    crops: list[Image.Image],
    expected: int,
    layout: dict,
    variant: int,
    extra_pad: bool,
    pad_ratio: int,
    src_boxes: list[dict] | None = None,
) -> tuple[Image.Image, list[Image.Image], dict]:
    expected = max(1, expected)
    while len(crops) < expected:
        crops.append(crops[-1].copy() if crops else Image.new("RGBA", (8, 8), CYAN_FILL))
    crops = crops[:expected]
    max_w = max(im.size[0] for im in crops)
    fh = max(im.size[1] for im in crops)
    pad = max(8, max_w // max(4, pad_ratio)) if extra_pad else 0
    fw = max_w + pad * 2
    sheet = Image.new("RGBA", (fw * expected, fh), CYAN_FILL)
    frames: list[Image.Image] = []
    packed_cells: list[dict] = []
    for i, crop in enumerate(crops):
        cell = Image.new("RGBA", (fw, fh), CYAN_FILL)
        dx = (fw - crop.size[0]) // 2
        dy = (fh - crop.size[1]) // 2
        cell.paste(crop, (dx, dy), crop)
        sheet.paste(cell, (i * fw, 0))
        frames.append(cell)
        packed_cells.append(
            {
                "x": i / expected,
                "y": 0.0,
                "w": 1 / expected,
                "h": 1.0,
                "px": {"x": i * fw, "y": 0, "w": fw, "h": fh},
                "src": (
                    src_boxes[i]
                    if src_boxes and i < len(src_boxes)
                    else {"x": 0, "y": 0, "w": crop.size[0], "h": crop.size[1]}
                ),
            }
        )
    meta = {
        "cells": packed_cells,
        "rows": 1,
        "detected": expected,
        "expected": expected,
        "packed": True,
        "frameWidth": fw,
        "frameHeight": fh,
        "variant": variant,
        "variant_label": SPLIT_VARIANT_LABELS[variant % SPLIT_VARIANT_COUNT],
        "runs": layout.get("runs") or [],
    }
    return sheet, frames, meta


def pack_uniform_strip(
    im: Image.Image,
    expected: int,
    variant: int = 0,
) -> tuple[Image.Image, list[Image.Image], dict]:
    """Cut a sprite strip into uniform cells. variant cycles different cut styles on the same source."""
    expected = max(1, int(expected or 1))
    variant = int(variant or 0) % SPLIT_VARIANT_COUNT
    src = im.convert("RGBA")
    # Variant 5: unpack 2×2 if the sheet really is a grid. A 1-row 4-frame
    # turnaround must not raise — 重新切分 used to get stuck on this method.
    if variant == 5 or (expected == 4 and looks_like_grid_2x2(src)):
        try:
            return pack_grid_2x2(src, variant=5)
        except ValueError:
            if variant == 5:
                variant = 2
    width, height = src.size
    layout = detect_strip_cells(src, expected)
    labels = label_strip_figures(src, layout)

    if variant in {1, 2}:
        crops: list[Image.Image] = []
        boxes: list[dict] = []
        if variant == 2:
            step = width / expected
            ranges = [
                (int(round(i * step)), int(round(width if i == expected - 1 else (i + 1) * step)))
                for i in range(expected)
            ]
        else:
            cells = layout.get("cells") or []
            ranges = []
            for i in range(expected):
                px = (cells[i].get("px") if i < len(cells) else None) or {}
                x0 = int(px.get("x") or 0)
                x1 = x0 + max(1, int(px.get("w") or width // expected))
                ranges.append((x0, min(width, x1)))
        for i, (x0, x1) in enumerate(ranges):
            x0 = max(0, min(width - 1, x0))
            x1 = max(x0 + 1, min(width, x1))
            crops.append(src.crop((x0, 0, x1, height)))
            boxes.append({"x": x0, "y": 0, "w": x1 - x0, "h": height})
        return _stack_frame_crops(
            crops,
            expected,
            layout,
            variant,
            extra_pad=variant == 1,
            pad_ratio=24,
            src_boxes=boxes,
        )

    pad_edge = 10 if variant == 3 else (0 if variant == 4 else 2)
    pad_ratio = 10 if variant == 3 else (22 if variant == 4 else 16)
    bboxes = figure_bboxes(labels, expected)
    content: list[tuple[int, int, int, int] | None] = []
    widths: list[int] = []
    for i in range(expected):
        bb = bboxes[i]
        if bb is None:
            content.append(None)
            continue
        x0 = max(0, bb[0] - pad_edge)
        y0 = max(0, bb[1] - pad_edge)
        x1 = min(width, bb[2] + pad_edge)
        y1 = min(height, bb[3] + pad_edge)
        content.append((x0, y0, x1, y1))
        widths.append(x1 - x0)
    max_w = max(widths) if widths else max(1, width // expected)
    max_w = min(max_w, max(8, int(width * 0.62)))
    pad = max(8, max_w // pad_ratio)
    fw = max_w + pad * 2
    fh = height
    sheet = Image.new("RGBA", (fw * expected, fh), CYAN_FILL)
    frames: list[Image.Image] = []
    packed_cells: list[dict] = []
    pix_src = src.load()
    for i in range(expected):
        cell = Image.new("RGBA", (fw, fh), CYAN_FILL)
        pix = cell.load()
        box = content[i]
        src_meta = {"x": 0, "y": 0, "w": 0, "h": 0}
        if box is not None:
            x0, y0, x1, y1 = box
            src_meta = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
            dest_x = (fw - (x1 - x0)) // 2
            for y in range(y0, y1):
                row = labels[y]
                for x in range(x0, x1):
                    if row[x] != i:
                        continue
                    dx = dest_x + (x - x0)
                    if 0 <= dx < fw:
                        pix[dx, y] = pix_src[x, y]
        sheet.paste(cell, (i * fw, 0))
        frames.append(cell)
        packed_cells.append(
            {
                "x": i / expected,
                "y": 0.0,
                "w": 1 / expected,
                "h": 1.0,
                "px": {"x": i * fw, "y": 0, "w": fw, "h": fh},
                "src": src_meta,
            }
        )
    last_i = max((i for i, box in enumerate(content) if box is not None), default=None)
    if last_i is not None:
        for i in range(last_i + 1, expected):
            frames[i] = frames[last_i].copy()
            sheet.paste(frames[i], (i * fw, 0))
            packed_cells[i]["src"] = dict(packed_cells[last_i]["src"])
    meta = {
        "cells": packed_cells,
        "rows": 1,
        "detected": expected,
        "expected": expected,
        "packed": True,
        "frameWidth": fw,
        "frameHeight": fh,
        "variant": variant,
        "variant_label": SPLIT_VARIANT_LABELS[variant],
        "runs": layout.get("runs") or [],
    }
    return sheet, frames, meta


def _cell_thumb(
    im: Image.Image,
    box: tuple[int, int],
    fg: tuple[int, int, int, int] | None = None,
    size: int = 48,
) -> list[int]:
    if fg:
        x0, y0, x1, y1 = fg
        cell = im.crop((x0, y0, x1 + 1, y1 + 1))
    else:
        x0, x1 = box
        cell = im.crop((x0, 0, max(x0 + 1, x1), im.size[1]))
    return list(cell.convert("L").resize((size, size), Image.Resampling.NEAREST).getdata())


def _mad(a: list[int], b: list[int]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / max(1, len(a))


def _unique_count(thumbs: list[list[int]], thresh: float) -> int:
    groups: list[list[int]] = []
    for t in thumbs:
        placed = False
        for g in groups:
            if _mad(t, g) < thresh:
                placed = True
                break
        if not placed:
            groups.append(t)
    return len(groups)


def _check(cid: str, title: str, score: int, detail: str, weight: int) -> dict:
    if score >= 80:
        status = "pass"
    elif score >= 50:
        status = "warn"
    else:
        status = "fail"
    return {"id": cid, "title": title, "score": score, "status": status, "detail": detail, "weight": weight}


def heuristic_score(png: bytes, slot: dict) -> dict:
    slot_id = slot["id"]
    kind = slot.get("kind") or "sprite"
    expected = FRAME_SLOTS.get(slot_id, 1)
    im = _open(png)
    w, h = im.size
    mask = _fg_mask(im)
    fg = sum(sum(row) for row in mask)
    total = w * h
    fg_ratio = fg / total if total else 0
    cyan_ratio = 1 - fg_ratio

    checks: list[dict] = []

    if kind == "cg":
        cyan_score = 100 if cyan_ratio < 0.08 else (40 if cyan_ratio < 0.25 else 10)
        checks.append(
            _check(
                "background",
                "插画底（不应是青屏）",
                cyan_score,
                f"青色/透明占比 {cyan_ratio:.0%}",
                20,
            )
        )
    else:
        keyed = Image.open(BytesIO(png)).convert("RGBA")
        alpha_zero = 0
        px = keyed.load()
        kw, kh = keyed.size
        sample = max(1, (kw * kh) // 80000)
        n = 0
        for y in range(0, kh, sample):
            for x in range(0, kw, sample):
                n += 1
                if px[x, y][3] < 16:
                    alpha_zero += 1
        alpha_ratio = alpha_zero / n if n else 0
        if alpha_ratio > 0.2:
            bg_score = 90 if 0.25 <= alpha_ratio <= 0.92 else 55
            detail = f"已是透明底 {alpha_ratio:.0%}"
        else:
            bg_score = 100 if cyan_ratio >= 0.35 else (60 if cyan_ratio >= 0.18 else 15)
            detail = f"青屏占比 {cyan_ratio:.0%}（精灵应大面积 #00FFFF）"
        checks.append(_check("background", "抠图底色", bg_score, detail, 18))

    columns = _split_columns(mask, expected)
    layout = detect_strip_cells(im, expected) if expected > 1 else None
    cells = (layout or {}).get("cells") or []
    nonempty = 0
    thumbs: list[list[int]] = []
    bottoms: list[float] = []
    occupancies: list[float] = []
    centers: list[float] = []
    heights: list[float] = []
    if cells:
        for cell in cells:
            x0 = max(0, int(round(cell["x"] * w)))
            y0 = max(0, int(round(cell["y"] * h)))
            x1 = min(w, int(round((cell["x"] + cell["w"]) * w)))
            y1 = min(h, int(round((cell["y"] + cell["h"]) * h)))
            box = _bbox(mask, x0, x1, y0, y1)
            cell_w = max(1, x1 - x0)
            cell_h = max(1, y1 - y0)
            if box:
                nonempty += 1
                bw = box[2] - box[0] + 1
                bh = box[3] - box[1] + 1
                occupancies.append((bw * bh) / (cell_w * cell_h))
                bottoms.append(box[3] / h)
                centers.append(((box[0] + box[2]) / 2 - x0) / cell_w)
                heights.append(bh / h)
                thumbs.append(_cell_thumb(im, (x0, x1), box))
            else:
                thumbs.append(_cell_thumb(im, (x0, x1)))
    else:
        for x0, x1 in columns:
            box = _bbox(mask, x0, x1)
            cell_w = max(1, x1 - x0)
            if box:
                nonempty += 1
                bw = box[2] - box[0] + 1
                bh = box[3] - box[1] + 1
                occupancies.append((bw * bh) / (cell_w * h))
                bottoms.append(box[3] / h)
                centers.append(((box[0] + box[2]) / 2 - x0) / cell_w)
                heights.append(bh / h)
                thumbs.append(_cell_thumb(im, (x0, x1), box))
            else:
                thumbs.append(_cell_thumb(im, (x0, x1)))

    if expected > 1:
        detected = int((layout or {}).get("detected") or nonempty)
        rows = int((layout or {}).get("rows") or 1)
        if rows != 1:
            layout_score = 12
            layout_detail = f"检出 {rows} 行 {detected} 格，必须单行正好 {expected} 格"
        elif detected != expected:
            layout_score = 18 if abs(detected - expected) > 1 else 38
            layout_detail = f"检出 {detected} 格，必须正好 {expected} 格单行"
        else:
            layout_score = 100 if nonempty == expected else min(90, int(100 * nonempty / expected))
            layout_detail = f"单行 {detected} 格，其中有前景 {nonempty} 格"
        checks.append(
            _check(
                "strip",
                f"分镜条（期望 {expected} 格）",
                layout_score,
                layout_detail,
                20,
            )
        )
        diffs = [_mad(thumbs[i], thumbs[i + 1]) for i in range(len(thumbs) - 1)] if len(thumbs) > 1 else [0]
        avg_d = mean(diffs) if diffs else 0
        lock_sheet = slot_id == "turnaround"
        unique = _unique_count(thumbs, 6.0 if slot_id == "idle" else 8.0)
        if lock_sheet:
            if avg_d < 3.5 or unique <= 1:
                div_score = 8
                div_detail = f"相邻格几乎一样（差 {avg_d:.1f}，独立朝向 {unique}），疑似同一张复制"
            elif avg_d < 10 or unique < 3:
                div_score = 48
                div_detail = f"朝向差偏弱（差 {avg_d:.1f}，独立朝向 {unique}），四视图应能分出正/侧/背"
            else:
                div_score = min(100, int(40 + avg_d * 2.2))
                div_detail = f"相邻格平均差 {avg_d:.1f}，独立朝向 {unique}，四朝向可分"
        elif slot_id == "idle":
            if unique <= 1 or avg_d < 2.2:
                div_score = 8
                div_detail = f"六帧同一张（差 {avg_d:.1f}，独立姿势 {unique}）"
            elif unique <= 2 or avg_d < 4:
                div_score = 45
                div_detail = f"呼吸差偏弱（差 {avg_d:.1f}，独立姿势 {unique}），胸肩应有起伏"
            else:
                div_score = min(100, int(45 + avg_d * 4))
                div_detail = f"呼吸差 {avg_d:.1f}，独立姿势 {unique}"
        else:
            if unique <= 2 or avg_d < 4:
                div_score = 8
                div_detail = f"关键帧在重复（差 {avg_d:.1f}，独立姿势 {unique}/{expected}）"
            elif unique < max(4, expected - 2) or avg_d < 10:
                div_score = 40
                div_detail = f"动作差不够（差 {avg_d:.1f}，独立姿势 {unique}/{expected}），动画会抖"
            else:
                div_score = min(100, int(30 + avg_d * 2.0 + unique * 5))
                div_detail = f"相邻格平均差 {avg_d:.1f}，独立姿势 {unique}/{expected}"
        checks.append(
            _check(
                "diversity",
                "四视图差异（闸门）" if lock_sheet else "帧差异（动画可用性）",
                div_score,
                div_detail,
                22,
            )
        )
    else:
        checks.append(_check("strip", "单幅构图", 80 if fg_ratio > 0.04 else 20, f"前景 {fg_ratio:.0%}", 10))

    if occupancies:
        occ = mean(occupancies)
        lock_sheet = slot_id == "turnaround"
        lo90, hi90 = (0.08, 0.70) if lock_sheet else (0.10, 0.58)
        lo60, hi60 = (0.05, 0.82) if lock_sheet else (0.06, 0.72)
        if lo90 <= occ <= hi90:
            occ_score = 90
        elif lo60 <= occ <= hi60:
            occ_score = 60
        else:
            occ_score = 25
        checks.append(
            _check(
                "scale",
                "身形占格（闸门可读）" if lock_sheet else "身形占格（对战可读）",
                occ_score,
                f"前景包围盒约占格 {occ:.0%}，过小看不清、过大易被裁切",
                16,
            )
        )
    else:
        checks.append(_check("scale", "身形占格（对战可读）", 10, "几乎没有前景", 16))

    if expected > 1 and len(centers) >= 3:
        cx_spread = pstdev(centers)
        h_spread = pstdev(heights) if len(heights) > 1 else 0
        airy = slot_id in AIR_SLOTS or slot_id in FALL_SLOTS
        size_spread = 0.0 if airy else h_spread
        if cx_spread < 0.06 and size_spread < 0.07:
            reg_score = 92
        elif cx_spread < 0.12 and size_spread < 0.14:
            reg_score = 55
        else:
            reg_score = 18
        size_note = "空中条不考身高" if airy else f"身高标准差 {size_spread:.3f}"
        checks.append(
            _check(
                "register",
                "帧对齐（位置/尺寸）",
                reg_score,
                f"格内水平中心标准差 {cx_spread:.3f}，{size_note}。应对齐在同一槽位，禁止人在条上平移",
                14,
            )
        )

    if kind == "cg":
        pass
    elif expected > 1 and slot_id not in AIR_SLOTS and slot_id not in FALL_SLOTS and len(bottoms) >= 3:
        spread = pstdev(bottoms) if len(bottoms) > 1 else 0
        base_score = 90 if spread < 0.045 else (55 if spread < 0.09 else 25)
        checks.append(
            _check(
                "baseline",
                "脚底基线",
                base_score,
                f"各帧脚底高度标准差 {spread:.3f}（待机/出招应落在同一地面）",
                12,
            )
        )
    elif slot_id in AIR_SLOTS and bottoms:
        label = "空中高度变化" if slot_id != "jump" else "跳跃高度变化"
        checks.append(
            _check(
                "baseline",
                label,
                80 if pstdev(bottoms) > 0.03 else 45,
                "空中条应有离地高度差，不能六帧都站在地面上",
                10,
            )
        )
    elif slot_id in FALL_SLOTS and bottoms:
        checks.append(
            _check(
                "baseline",
                "倒地高度变化",
                80 if pstdev(bottoms) > 0.03 else 45,
                "受击/战败应从站立落到倒地，不能六帧都站着",
                10,
            )
        )

    sharp = ImageStat.Stat(im.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]
    sharp_score = 85 if sharp > 12 else (50 if sharp > 5 else 20)
    checks.append(
        _check(
            "edges",
            "像素硬边",
            sharp_score,
            f"边缘能量 {sharp:.1f}（过低像照片/高斯糊）",
            12,
        )
    )

    weight_sum = sum(c["weight"] for c in checks) or 1
    pipeline = round(sum(c["score"] * c["weight"] for c in checks) / weight_sum)
    return {
        "pipeline": pipeline,
        "checks": checks,
        "meta": {
            "size": [w, h],
            "fg_ratio": round(fg_ratio, 4),
            "expected_frames": expected,
            "found_frames": nonempty,
        },
    }


def diversity_score(pipeline: dict) -> int | None:
    for c in pipeline.get("checks") or []:
        if c.get("id") == "diversity":
            try:
                return int(c.get("score") or 0)
            except (TypeError, ValueError):
                return 0
    return None


def _is_sheet_bg(r: int, g: int, b: int, a: int = 255) -> bool:
    """Cyan key / empty pixels — not character ink."""
    if a < 18:
        return True
    if r >= 125:
        return False
    gb = min(g, b)
    if gb < 100:
        return False
    if gb <= r + 24:
        return False
    if abs(g - b) > 78:
        return False
    return True


def ink_bbox(cell: Image.Image) -> tuple[int, int, int, int] | None:
    """Tight AABB of non-cyan ink inside one frame cell."""
    im = cell.convert("RGBA")
    w, h = im.size
    px = im.load()
    min_x, min_y, max_x, max_y = w, h, -1, -1
    step = 2 if max(w, h) > 280 else 1
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b, a = px[x, y]
            if _is_sheet_bg(r, g, b, a):
                continue
            if x < min_x:
                min_x = x
            if y < min_y:
                min_y = y
            if x > max_x:
                max_x = x
            if y > max_y:
                max_y = y
    if max_x < min_x:
        return None
    # Expand 1px for step sampling
    return (
        max(0, min_x - step + 1),
        max(0, min_y - step + 1),
        min(w - 1, max_x + step - 1),
        min(h - 1, max_y + step - 1),
    )


def _body_metric(bw: int, bh: int) -> int:
    """Standing height proxy. Prone/wide poses use width so we don't explode scale."""
    if bw > bh * 1.18:
        return max(bh, int(bw * 0.52))
    return max(1, bh)


def measure_cell_body(cell: Image.Image) -> dict:
    """
    Estimate character *figure* scale, not full prop/FX ink AABB.

    Weapons and particles often make a tall sparse spike above the head; we take the
    densest vertical band (row occupancy) as the body core. Crouched/balled poses
    get a mild width floor so they are not treated as a tiny standing figure.
    """
    im = cell.convert("RGBA")
    w, h = im.size
    if w < 4 or h < 4:
        return {"body_h": 0, "feet_y": h - 1, "head_y": 0, "dense_h": 0, "torso_w": 0, "ink_h": 0}

    px = im.load()
    # Prefer the central column band so side-held weapons don't dominate occupancy.
    x_lo = int(w * 0.18)
    x_hi = max(x_lo + 1, int(w * 0.82))
    row_count = [0] * h
    row_run_w = [0] * h  # longest contiguous ink run in the central band
    ink_min_y, ink_max_y = h, -1
    for y in range(h):
        run = 0
        best_run = 0
        c = 0
        for x in range(x_lo, x_hi):
            r, g, b, a = px[x, y]
            if _is_sheet_bg(r, g, b, a):
                if run:
                    best_run = max(best_run, run)
                    run = 0
                continue
            c += 1
            run += 1
            if y < ink_min_y:
                ink_min_y = y
            if y > ink_max_y:
                ink_max_y = y
        if run:
            best_run = max(best_run, run)
        row_count[y] = c
        row_run_w[y] = best_run

    # Full-frame ink height (diagnostics / fallback)
    full_min_y, full_max_y = h, -1
    for y in range(h):
        for x in range(0, w, 2):
            r, g, b, a = px[x, y]
            if _is_sheet_bg(r, g, b, a):
                continue
            if y < full_min_y:
                full_min_y = y
            if y > full_max_y:
                full_max_y = y
            break
    if full_max_y < full_min_y:
        return {"body_h": 0, "feet_y": h - 1, "head_y": 0, "dense_h": 0, "torso_w": 0, "ink_h": 0}

    if ink_max_y < ink_min_y:
        ink_min_y, ink_max_y = full_min_y, full_max_y

    ink_h = full_max_y - full_min_y + 1
    peak = max(row_count[ink_min_y : ink_max_y + 1] or [0])
    if peak < 3:
        return {
            "body_h": ink_h,
            "feet_y": full_max_y,
            "head_y": full_min_y,
            "dense_h": ink_h,
            "torso_w": 0,
            "ink_h": ink_h,
        }

    # Ignore thin weapon shafts / particle trails (low occupancy in the body column).
    band_w = max(1, x_hi - x_lo)
    thr = max(5, min(int(peak * 0.30), int(band_w * 0.12)))
    thr = min(thr, max(3, peak - 1))

    def best_dense_run(threshold: int) -> tuple[int, int] | None:
        # Allow thin belt / sash holes so feet stay at boots, not mid-torso.
        max_gap = max(2, min(14, h // 40))
        best: tuple[int, int, float] | None = None
        y = ink_min_y
        while y <= ink_max_y:
            if row_count[y] < threshold:
                y += 1
                continue
            y0 = y
            gap = 0
            y1 = y
            score = 0.0
            while y <= ink_max_y:
                if row_count[y] >= threshold:
                    gap = 0
                    y1 = y
                    score += row_count[y]
                    y += 1
                elif gap < max_gap:
                    gap += 1
                    y += 1
                else:
                    break
            cand = (y0, y1, score)
            if best is None or cand[2] > best[2] or (
                cand[2] == best[2] and (cand[1] - cand[0]) > (best[1] - best[0])
            ):
                best = cand
            y = max(y, y1 + 1)
        if not best:
            return None
        return best[0], best[1]

    run = best_dense_run(thr)
    if run is None or (run[1] - run[0] + 1) < max(12, int(ink_h * 0.18)):
        run = best_dense_run(max(3, thr // 2)) or (ink_min_y, ink_max_y)

    head_y, feet_y = run
    dense_h = feet_y - head_y + 1

    mid0 = head_y + max(1, int(dense_h * 0.30))
    mid1 = head_y + max(mid0 + 1, int(dense_h * 0.70))
    widths = [row_run_w[y] for y in range(mid0, min(feet_y, mid1) + 1) if row_run_w[y] > 0]
    torso_w = int(median(widths)) if widths else 0

    # Default: dense core height (hat/head mass → feet), not full prop AABB.
    body_h = dense_h
    # Only boost scrunched poses (crouch/ball) via torso width — never inflate wide stances.
    if torso_w > 8 and dense_h < int(torso_w * 1.35):
        body_h = max(dense_h, int(torso_w * 1.9))

    return {
        "body_h": max(1, int(body_h)),
        "feet_y": int(feet_y),
        "head_y": int(head_y),
        "dense_h": int(dense_h),
        "torso_w": int(torso_w),
        "ink_h": int(ink_h),
    }


def measure_strip_body(im: Image.Image, frames: int) -> dict:
    """Median core-body metric + feet Y across cells of a packed strip."""
    frames = max(1, int(frames or 1))
    src = im.convert("RGBA")
    w, h = src.size
    fw = max(1, w // frames)
    metrics: list[int] = []
    feet: list[int] = []
    dense: list[int] = []
    for i in range(frames):
        cell = src.crop((i * fw, 0, min(w, (i + 1) * fw), h))
        m = measure_cell_body(cell)
        if not m.get("body_h"):
            continue
        metrics.append(int(m["body_h"]))
        feet.append(int(m["feet_y"]))
        dense.append(int(m.get("dense_h") or m["body_h"]))
    if not metrics:
        return {
            "body_h": 0,
            "feet_y": h - 8,
            "frame_w": fw,
            "frame_h": h,
            "frames": frames,
            "dense_h": 0,
            "ink_h": 0,
        }
    return {
        "body_h": int(median(metrics)),
        "feet_y": int(median(feet)),
        "dense_h": int(median(dense)) if dense else 0,
        "frame_w": fw,
        "frame_h": h,
        "frames": frames,
    }


def rescale_strip_to_body(
    im: Image.Image,
    frames: int,
    target_body_h: int,
    target_feet_y: int,
    target_frame_h: int | None = None,
    *,
    tol: float = 0.035,
    preserve_air_lift: bool = False,
) -> tuple[Image.Image, dict]:
    """
    Rebuild a character strip so each frame's *core body* scale ≈ target_body_h,
    with core feet pinned near target_feet_y. Full ink (weapons/FX) is kept, but
    does not drive the scale. Pixel-art: NEAREST.

    preserve_air_lift: for jump/air strips, keep each frame's feet height relative
    to the most grounded frame in the strip (apex stays above the head guide).
    """
    frames = max(1, int(frames or 1))
    target_body_h = max(24, int(target_body_h))
    src = im.convert("RGBA")
    w, h = src.size
    fw = max(1, w // frames)
    measured = measure_strip_body(src, frames)
    cur_h = measured["body_h"] or 0
    if cur_h <= 0:
        return src.copy(), {"skipped": True, "reason": "no_ink", "before": 0, "after": 0, "scale": 1.0}
    avg_scale = target_body_h / cur_h
    if abs(avg_scale - 1.0) <= tol:
        return src.copy(), {
            "skipped": True,
            "reason": "already_close",
            "before": cur_h,
            "after": cur_h,
            "scale": round(avg_scale, 4),
        }

    cell_cores: list[dict | None] = []
    cells: list[Image.Image] = []
    for i in range(frames):
        cell = src.crop((i * fw, 0, min(w, (i + 1) * fw), h))
        cells.append(cell)
        core = measure_cell_body(cell)
        if not core.get("body_h"):
            cell_cores.append(None)
        else:
            cell_cores.append(core)
    lifts = air_lifts_from_cells(cells) if preserve_air_lift else [0] * frames

    prepared: list[dict] = []
    scales: list[float] = []
    max_fw = fw
    # First pass: scale factors + desired tops (for shared y_shift).
    cell_plans: list[dict] = []
    for i in range(frames):
        cell = src.crop((i * fw, 0, min(w, (i + 1) * fw), h))
        core = cell_cores[i]
        bb = ink_bbox(cell)
        if not bb or not core or not core.get("body_h"):
            cell_plans.append({"empty": True, "cell": cell})
            continue
        x0, y0, x1, y1 = bb
        metric = max(1, int(core["body_h"]))
        scale = max(0.35, min(3.0, target_body_h / metric))
        scales.append(scale)
        pad = 6
        crop_box = (
            max(0, x0 - pad),
            max(0, y0 - pad),
            min(cell.size[0], x1 + 1 + pad),
            min(cell.size[1], y1 + 1 + pad),
        )
        crop = cell.crop(crop_box)
        nw = max(1, int(round(crop.size[0] * scale)))
        nh = max(1, int(round(crop.size[1] * scale)))
        scaled = crop.resize((nw, nh), Image.Resampling.NEAREST)
        core_feet = int(core["feet_y"])
        feet_in_crop = (core_feet - crop_box[1]) + 1
        feet_scaled = max(1, int(round(feet_in_crop * scale)))
        lift = int(round(lifts[i] * scale))
        pin_feet = int(target_feet_y) - lift
        top = pin_feet - feet_scaled + 1
        cell_plans.append(
            {
                "empty": False,
                "scaled": scaled,
                "nh": nh,
                "nw": nw,
                "top": top,
                "pin_feet": pin_feet,
                "lift": lift,
                "feet_scaled": feet_scaled,
            }
        )
    y_shift = max(
        0,
        max((-int(p["top"]) for p in cell_plans if not p.get("empty")), default=0),
    )
    fh_needed = int(target_frame_h or h) + y_shift
    for p in cell_plans:
        if p.get("empty"):
            prepared.append(p)
            continue
        top = int(p["top"]) + y_shift
        pin_feet = int(p["pin_feet"]) + y_shift
        nh = int(p["nh"])
        nw = int(p["nw"])
        cell_w = max(fw, nw + 20)
        cell_h = max(fh_needed, top + nh + 10, pin_feet + 10, nh + 20)
        fh_needed = max(fh_needed, cell_h)
        max_fw = max(max_fw, cell_w)
        prepared.append(
            {
                "empty": False,
                "scaled": p["scaled"],
                "top": top,
                "nh": nh,
                "lift": p["lift"],
            }
        )

    fh = max(fh_needed, int(target_frame_h or h) + y_shift, int(target_feet_y) + y_shift + 12)
    fw_u = max_fw
    sheet = Image.new("RGBA", (fw_u * frames, fh), CYAN_FILL)
    for i, item in enumerate(prepared):
        cell_canvas = Image.new("RGBA", (fw_u, fh), CYAN_FILL)
        if item.get("empty"):
            orig = item["cell"]
            ow, oh = orig.size
            cell_canvas.paste(orig, ((fw_u - ow) // 2, max(0, min(fh - oh, (fh - oh) // 2))), orig)
        else:
            scaled = item["scaled"]
            nh = item["nh"]
            top = max(0, min(fh - nh, int(item["top"])))
            left = (fw_u - scaled.size[0]) // 2
            cell_canvas.paste(scaled, (left, top), scaled)
        sheet.paste(cell_canvas, (i * fw_u, 0))

    after = measure_strip_body(sheet, frames)["body_h"]
    return sheet, {
        "skipped": False,
        "before": cur_h,
        "after": after,
        "scale": round(mean(scales) if scales else avg_scale, 4),
        "frame_w": fw_u,
        "frame_h": fh,
        "frames": frames,
        "preserve_air_lift": bool(preserve_air_lift),
        "air_lifts": lifts if preserve_air_lift else [],
        "y_shift": y_shift,
    }
