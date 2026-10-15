"""
visual_diff.py — compares two screenshots and finds the regions that changed (requirement 6), plus
the crop and thumbnail images saved with each snapshot.

Who uses it: routes/compare.py (Compare page), alerts.py (email image), checker.py (crops/thumbnails).
Depends on: Pillow only (no numpy), so it's simple to install and explain.

The algorithm:
1. Pad both screenshots to the same size (white background).
2. Shift detection. If someone inserted a paragraph near the top, everything below moves down, and a
   naive pixel comparison would mark the whole rest of the page as changed. So on small grayscale copies
   we find the first row that differs, then try sliding the old image's lower part up/down by
   -600…+600 px (8 px steps) and keep the offset where the two images match best. We report it as
   `shifted_by_px` and compare the aligned images.
3. Pixel difference (ImageChops.difference) → grayscale → threshold (>30) → dilate (MaxFilter) so
   nearby changed pixels merge into blobs.
4. Divide the page into 16 px cells, mark cells containing changed pixels, and flood-fill connected
   cells into rectangles: these are the `regions` we draw as glowing boxes.
5. Bake a copy of the new screenshot with translucent red boxes (used in emails), and cache everything.
"""
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

from .config import data_path

CELL = 16
SCALE = 4  # shift search works on images 4x smaller (fast)
MAX_SHIFT = 600
SHIFT_STEP = 8
THRESHOLD = 30
MAX_REGIONS = 60


@dataclass
class VisualResult:
    width: int
    height_before: int
    height_after: int
    regions: list[dict]
    changed_percent: float
    shifted_by_px: int


def _pad(img: Image.Image, width: int, height: int) -> Image.Image:
    if img.size == (width, height):
        return img
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(img, (0, 0))
    return canvas


def _row_diff_start(a: Image.Image, b: Image.Image) -> int | None:
    """First row (in the small images) where the two differ noticeably, or None if identical."""
    diff = ImageChops.difference(a, b)
    w, h = diff.size
    for y in range(h):
        row = diff.crop((0, y, w, y + 1))
        if ImageStat.Stat(row).mean[0] > 2.0:
            return y
    return None


def _mean_diff(a: Image.Image, b: Image.Image) -> float:
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def detect_shift(before: Image.Image, after: Image.Image) -> tuple[int, int]:
    """Return (first_diff_row_px, shift_px). shift > 0 means content moved DOWN in the new version."""
    small_a = before.convert("L").resize((before.width // SCALE, before.height // SCALE))
    small_b = after.convert("L").resize((after.width // SCALE, after.height // SCALE))
    start = _row_diff_start(small_a, small_b)
    if start is None:
        return 0, 0
    h = small_a.height
    w = small_a.width
    best_shift, best_score = 0, None
    max_s = MAX_SHIFT // SCALE
    step = max(1, SHIFT_STEP // SCALE)
    for s in range(-max_s, max_s + 1, step):
        # Compare old rows [start, h - |s|) against new rows shifted by s.
        a_top, a_bottom = start, h - max(0, s)
        b_top = start + s
        if b_top < 0:
            a_top -= b_top
            b_top = 0
        length = min(a_bottom - a_top, h - b_top)
        if length < 20:
            continue
        a_crop = small_a.crop((0, a_top, w, a_top + length))
        b_crop = small_b.crop((0, b_top, w, b_top + length))
        score = _mean_diff(a_crop, b_crop)
        if best_score is None or score < best_score - 0.01 or (abs(score - best_score) <= 0.01 and abs(s) < abs(best_shift)):
            best_score, best_shift = score, s
    return start * SCALE, best_shift * SCALE


def _regions_from_mask(mask: Image.Image) -> tuple[list[dict], float]:
    """Group changed 16 px cells into rectangles with a flood fill. Returns (regions, changed_percent)."""
    w, h = mask.size
    cols, rows = (w + CELL - 1) // CELL, (h + CELL - 1) // CELL
    # A cell is "changed" if any pixel in it is set: resizing with BOX averages, so > 0 means some pixel.
    small = mask.resize((cols, rows), Image.Resampling.BOX)
    px = small.load()
    changed = [[px[c, r] > 0 for c in range(cols)] for r in range(rows)]
    seen = [[False] * cols for _ in range(rows)]
    regions: list[dict] = []
    changed_cells = 0
    for r in range(rows):
        for c in range(cols):
            if not changed[r][c] or seen[r][c]:
                continue
            stack = [(r, c)]
            seen[r][c] = True
            r1 = r2 = r
            c1 = c2 = c
            while stack:
                cr, cc = stack.pop()
                changed_cells += 1
                r1, r2, c1, c2 = min(r1, cr), max(r2, cr), min(c1, cc), max(c2, cc)
                for nr, nc in ((cr + 1, cc), (cr - 1, cc), (cr, cc + 1), (cr, cc - 1)):
                    if 0 <= nr < rows and 0 <= nc < cols and changed[nr][nc] and not seen[nr][nc]:
                        seen[nr][nc] = True
                        stack.append((nr, nc))
            regions.append({"x": c1 * CELL, "y": r1 * CELL, "w": (c2 - c1 + 1) * CELL, "h": (r2 - r1 + 1) * CELL})
    regions.sort(key=lambda g: -(g["w"] * g["h"]))
    percent = round(100 * changed_cells / max(1, cols * rows), 2)
    return regions[:MAX_REGIONS], percent


def compare_images(before_path: Path, after_path: Path) -> tuple[VisualResult, Image.Image]:
    """Run the full algorithm. Returns the result and the highlighted 'after' image."""
    before = Image.open(before_path).convert("RGB")
    after = Image.open(after_path).convert("RGB")
    hb, ha = before.height, after.height
    width = max(before.width, after.width)
    height = max(hb, ha)
    before_p, after_p = _pad(before, width, height), _pad(after, width, height)

    start, shift = detect_shift(before_p, after_p)
    aligned = before_p
    if shift:
        # Build an "old image moved by `shift`" so unchanged content lines up with the new image.
        aligned = Image.new("RGB", (width, height), "white")
        aligned.paste(before_p.crop((0, 0, width, start)), (0, 0))
        moved = before_p.crop((0, start, width, height))
        aligned.paste(moved, (0, start + shift))

    # Work at half resolution for speed; regions are scaled back up.
    half = (max(1, width // 2), max(1, height // 2))
    diff = ImageChops.difference(aligned.resize(half), after_p.resize(half)).convert("L")
    mask = diff.point(lambda v: 255 if v > THRESHOLD else 0)
    mask = mask.filter(ImageFilter.MaxFilter(5))  # dilate (≈ MaxFilter(9) at full size)
    regions_half, percent = _regions_from_mask(mask)
    regions = [{k: v * 2 for k, v in r.items()} for r in regions_half]
    regions = [r for r in regions if r["y"] < ha]

    highlighted = after.copy().convert("RGBA")
    overlay = Image.new("RGBA", highlighted.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for r in regions:
        box = (r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"])
        draw.rectangle(box, fill=(240, 96, 127, 46), outline=(220, 40, 80, 220), width=3)
    highlighted = Image.alpha_composite(highlighted, overlay).convert("RGB")
    return VisualResult(width, hb, ha, regions, percent, shift), highlighted


def cached_compare(a_id: int, b_id: int, before_path: Path, after_path: Path) -> VisualResult:
    """compare_images with an on-disk cache keyed by the two snapshot ids."""
    json_path = data_path("diffs", f"{a_id}_{b_id}.json")
    png_path = data_path("diffs", f"{a_id}_{b_id}.png")
    if json_path.exists() and png_path.exists():
        return VisualResult(**json.loads(json_path.read_text()))
    result, highlighted = compare_images(before_path, after_path)
    highlighted.save(png_path, optimize=True)
    json_path.write_text(json.dumps(asdict(result)))
    return result


def diff_image_path(a_id: int, b_id: int) -> Path:
    return data_path("diffs", f"{a_id}_{b_id}.png")


# ---------- crops and thumbnails for snapshots ----------

def union_box(boxes: dict, selectors: list[str]) -> dict | None:
    """Smallest rectangle covering every watched selector's box (from the fetcher)."""
    found = [boxes[s] for s in selectors if s in boxes]
    if not found:
        return None
    x1 = min(b["x"] for b in found)
    y1 = min(b["y"] for b in found)
    x2 = max(b["x"] + b["w"] for b in found)
    y2 = max(b["y"] + b["h"] for b in found)
    return {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}


def save_crop(screenshot_path: Path, box: dict, out: Path, pad: int = 12) -> bool:
    """Crop the watched region out of the full screenshot (with a little padding)."""
    with Image.open(screenshot_path) as img:
        x1 = max(0, box["x"] - pad)
        y1 = max(0, box["y"] - pad)
        x2 = min(img.width, box["x"] + box["w"] + pad)
        y2 = min(img.height, box["y"] + box["h"] + pad)
        if x2 - x1 < 4 or y2 - y1 < 4:
            return False
        img.crop((x1, y1, x2, y2)).save(out, optimize=True)
    return True


def save_thumbnail(source: Path, out: Path, width: int = 480, max_ratio: float = 0.66) -> None:
    """A 480 px-wide JPEG: the crop if there is one, otherwise the top of the page."""
    with Image.open(source) as img:
        img = img.convert("RGB")
        crop_h = min(img.height, int(img.width * max_ratio))
        img = img.crop((0, 0, img.width, crop_h))
        height = max(1, int(img.height * width / img.width))
        img.resize((width, height), Image.Resampling.LANCZOS).save(out, "JPEG", quality=78, optimize=True)
