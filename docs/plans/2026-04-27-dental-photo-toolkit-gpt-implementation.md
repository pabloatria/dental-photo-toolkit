# Dental Photo Toolkit GPT — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the file artifacts (pipeline + instructions + knowledge + welcome + README) that Pablo uploads to ChatGPT to create a Custom GPT, mirroring the existing Claude skill pipeline minus RAW support.

**Architecture:** Single-file Python pipeline (`pipeline.py`) executes inside ChatGPT's Code Interpreter sandbox. Two markdown knowledge files (AACD standards, filename conventions) provide reference for the GPT to consult. A system-prompt file (`instructions.md`) drives behavior; a welcome message file sets user-facing guidelines. README walks Pablo through the GPT Store publishing flow.

**Tech Stack:** Python 3.11, numpy, opencv-python, Pillow (all available in Code Interpreter). No rawpy. No external services. No backend.

**Companion design doc:** `docs/plans/2026-04-27-dental-photo-toolkit-gpt-design.md`

**Reference source:** `dental-photo-processor/` (existing Claude skill, working pipeline)

---

## Task 1: Scaffold the GPT project folder

**Files:**
- Create: `dental-photo-toolkit-gpt/` (directory)
- Create: `dental-photo-toolkit-gpt/knowledge/` (directory)
- Create: `dental-photo-toolkit-gpt/.gitkeep` files where needed

**Step 1: Create directories**

```bash
mkdir -p /Users/pabloatria/Downloads/photo-skill/dental-photo-toolkit-gpt/knowledge
```

**Step 2: Verify**

```bash
ls -la /Users/pabloatria/Downloads/photo-skill/dental-photo-toolkit-gpt/
```
Expected: `knowledge/` directory exists.

**Step 3: Commit**

```bash
cd /Users/pabloatria/Downloads/photo-skill
git add dental-photo-toolkit-gpt/
git commit -m "scaffold: dental-photo-toolkit-gpt directory"
```

(If `git add` finds nothing because the directory is empty, defer the commit until Task 2 produces a file.)

---

## Task 2: Build the single-file pipeline.py (JPEG-only, merged from skill)

**Files:**
- Create: `dental-photo-toolkit-gpt/pipeline.py`
- Reference (read-only): `dental-photo-processor/scripts/{classify,white_balance,crop_aacd,composite,process_photos}.py`

**Step 1: Write the failing smoke test**

Create `dental-photo-toolkit-gpt/test_pipeline.py`:

```python
"""Smoke test: run pipeline on a synthetic JPEG case, assert outputs exist."""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
SYNTH_SCRIPT = ROOT / "dental-photo-processor" / "scripts" / "_make_test_case.py"


def test_pipeline_end_to_end(tmp_path):
    case = tmp_path / "case"
    subprocess.run([sys.executable, str(SYNTH_SCRIPT), str(case)], check=True)
    out_zip = tmp_path / "out.zip"
    subprocess.run(
        [sys.executable, str(HERE / "pipeline.py"), str(case), "--output", str(out_zip)],
        check=True,
    )
    assert out_zip.exists()
    with zipfile.ZipFile(out_zip) as z:
        names = z.namelist()
    assert any("aacd_board" in n for n in names), f"no AACD board in zip: {names}"
    assert any("before_after" in n for n in names), f"no before/after in zip: {names}"
    assert any("manifest.csv" in n for n in names)
    assert any("report.md" in n for n in names)
```

**Step 2: Run test, expect failure**

```bash
cd /Users/pabloatria/Downloads/photo-skill/dental-photo-toolkit-gpt
python3 -m pytest test_pipeline.py -v
```
Expected: FAIL — `pipeline.py` does not exist yet.

**Step 3: Write `pipeline.py` (single-file merged pipeline, RAW stripped)**

Merge `classify.py`, `white_balance.py`, `crop_aacd.py`, `composite.py`, `process_photos.py` from the Claude skill into one file. Key changes from the skill:

1. Drop the `rawpy` import and the RAW branch in `_read_image`.
2. Restrict `IMAGE_EXTS` to `{".jpg", ".jpeg", ".png", ".tif", ".tiff"}`.
3. CLI `--output` flag: write outputs to a temp dir, then zip to the path given.
4. Default behavior when `--output` is a `.zip` path: zip and clean up the temp dir.
5. Add a `--watermark/--no-watermark` flag (default `--watermark`).

Full code for `dental-photo-toolkit-gpt/pipeline.py`:

```python
"""Dental Photo Toolkit — single-file pipeline for ChatGPT Code Interpreter.

Mirrors the dental-photo-processor Claude skill, JPEG/PNG/TIFF only.
See docs/plans/2026-04-27-dental-photo-toolkit-gpt-design.md for context.

Usage:
    python pipeline.py <case-folder> --output <out.zip>
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np

# ---------------------------------------------------------------- classify

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

TIMEPOINT_PATTERNS = {
    "before": [r"\bpre\b", r"\bbefore\b", r"\bantes\b", r"\binicial\b", r"\binitial\b"],
    "after":  [r"\bpost\b", r"\bafter\b", r"\bdespues\b", r"\bdespués\b", r"\bfinal\b"],
    "interim": [r"\bintra\b", r"\bprov\b", r"\bprovisional\b"],
}

POLARIZATION_PATTERNS = {
    "polarized": [r"_pol\b", r"_xp\b", r"_cross\b", r"_polar\b", r"_xpl\b"],
    "non_polarized_explicit": [r"_np\b", r"_nopol\b", r"_normal\b"],
}

VIEW_PATTERNS = {
    1:  ["face_smile", "fullface_smile", "cara_sonrisa", "smile_natural"],
    2:  ["face_repose", "fullface_repose", "cara_reposo", "repose"],
    3:  ["profile", "perfil"],
    4:  ["smile_wide", "wide_smile", "sonrisa_amplia", "smile_1to2"],
    5:  ["right_smile", "derecha_sonrisa", "buccal_right", "smile_right"],
    6:  ["left_smile", "izquierda_sonrisa", "buccal_left", "smile_left"],
    7:  ["retracted_apart", "frontal_apart", "abierta", "teeth_apart"],
    8:  ["retracted_mip", "frontal_together", "mip", "teeth_together"],
    9:  ["retracted_right", "lateral_right", "lat_der", "retraido_derecha"],
    10: ["retracted_left", "lateral_left", "lat_izq", "retraido_izquierda"],
    11: ["occlusal_max", "oclusal_sup", "upper_occlusal", "maxillary_occlusal"],
    12: ["occlusal_mand", "oclusal_inf", "lower_occlusal", "mandibular_occlusal"],
    13: ["1to1", "oneone", "close_anterior", "anterior_closeup"],
}

VIEW_LABELS = {
    1: "Full face — smile",
    2: "Full face — repose",
    3: "Profile",
    4: "Wide smile (1:2)",
    5: "Right buccal smile",
    6: "Left buccal smile",
    7: "Retracted frontal — apart",
    8: "Retracted frontal — MIP",
    9: "Retracted right lateral",
    10: "Retracted left lateral",
    11: "Maxillary occlusal",
    12: "Mandibular occlusal",
    13: "EAED 1:1 anterior close-up",
}


@dataclass
class PhotoRecord:
    path: str
    timepoint: str
    polarization: str
    view_number: int
    view_label: str
    notes: str = ""


def _matches_any(haystack: str, patterns: list[str]) -> bool:
    return any(re.search(p, haystack) for p in patterns)


def _detect_timepoint(path: Path, root: Path) -> str:
    rel = str(path.relative_to(root)).lower().replace("\\", "/")
    for label, patterns in TIMEPOINT_PATTERNS.items():
        if _matches_any(rel, patterns):
            return label
    return "unknown"


def _detect_polarization(name_lower: str) -> str:
    if _matches_any(name_lower, POLARIZATION_PATTERNS["polarized"]):
        return "polarized"
    return "non_polarized"


def _detect_view(name_lower: str) -> int:
    for view_num, keywords in VIEW_PATTERNS.items():
        for kw in keywords:
            if kw in name_lower:
                return view_num
    return 0


def scan_case(case_folder: Path) -> list[PhotoRecord]:
    records: list[PhotoRecord] = []
    for path in sorted(case_folder.rglob("*")):
        if path.is_dir():
            continue
        if path.suffix.lower() not in IMAGE_EXTS:
            continue
        if "_processed" in path.parts:
            continue
        name_lower = path.name.lower()
        rel_lower = str(path.relative_to(case_folder)).lower().replace("\\", "/")
        timepoint = _detect_timepoint(path, case_folder)
        polarization = _detect_polarization(name_lower)
        view_num = _detect_view(rel_lower)
        notes = []
        if timepoint == "unknown":
            notes.append("timepoint unresolved")
        if view_num == 0:
            notes.append("view unresolved")
        records.append(PhotoRecord(
            path=str(path), timepoint=timepoint, polarization=polarization,
            view_number=view_num, view_label=VIEW_LABELS.get(view_num, "unknown"),
            notes="; ".join(notes),
        ))
    return records


# ---------------------------------------------------------------- white balance

SPECULAR_PERCENTILE = 99
SPECULAR_AB_TOLERANCE = 5
MIN_SPECULAR_PIXELS = 1000
GRAYWORLD_DAMPING = 0.6
SKIN_LAB_RANGE = ((30, 5, 10), (80, 25, 35))
SKIN_ANCHOR_AB = (15.0, 18.0)
SKIN_PROTECTION_THRESHOLD = 6.0


@dataclass
class WBResult:
    image: np.ndarray
    tier: str
    gain_rgb: tuple
    correction_magnitude: float
    notes: str = ""


def _read_image(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Could not read {path}")
    return img


def _apply_gain(img, gain_bgr):
    out = img.astype(np.float32)
    out[..., 0] *= gain_bgr[0]
    out[..., 1] *= gain_bgr[1]
    out[..., 2] *= gain_bgr[2]
    return np.clip(out, 0, 255).astype(np.uint8)


def _intraoral_wb(img: np.ndarray) -> WBResult:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    L, a, b = cv2.split(lab)
    L_thresh = np.percentile(L, SPECULAR_PERCENTILE)
    a_centered = a.astype(np.int16) - 128
    b_centered = b.astype(np.int16) - 128
    mask = (
        (L >= L_thresh)
        & (np.abs(a_centered) < SPECULAR_AB_TOLERANCE)
        & (np.abs(b_centered) < SPECULAR_AB_TOLERANCE)
    )
    if int(mask.sum()) >= MIN_SPECULAR_PIXELS:
        sample = img[mask]
        mean_bgr = sample.mean(axis=0)
        gray = mean_bgr.mean()
        gain = (gray / max(mean_bgr[0], 1e-6),
                gray / max(mean_bgr[1], 1e-6),
                gray / max(mean_bgr[2], 1e-6))
        return WBResult(_apply_gain(img, gain), "intraoral",
                        (gain[2], gain[1], gain[0]), 0.0,
                        "enamel-highlight sampling")
    flat = img.reshape(-1, 3).astype(np.float32)
    L_flat = L.flatten()
    keep = (L_flat > np.percentile(L_flat, 5)) & (L_flat < np.percentile(L_flat, 99.9))
    mean_bgr = flat[keep].mean(axis=0)
    gray = mean_bgr.mean()
    raw_gain = np.array([gray / max(mean_bgr[0], 1e-6),
                         gray / max(mean_bgr[1], 1e-6),
                         gray / max(mean_bgr[2], 1e-6)])
    damped = 1.0 + (raw_gain - 1.0) * GRAYWORLD_DAMPING
    gain = tuple(damped.tolist())
    return WBResult(_apply_gain(img, gain), "intraoral",
                    (gain[2], gain[1], gain[0]), 0.0,
                    "damped gray-world (insufficient highlights)")


def _portrait_wb(img: np.ndarray) -> WBResult:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    (Lmin, amin, bmin), (Lmax, amax, bmax) = SKIN_LAB_RANGE
    L, a, b = cv2.split(lab)
    a_signed = a.astype(np.int16) - 128
    b_signed = b.astype(np.int16) - 128
    skin_mask = (
        (L >= Lmin) & (L <= Lmax)
        & (a_signed >= amin) & (a_signed <= amax)
        & (b_signed >= bmin) & (b_signed <= bmax)
    )
    non_skin = ~skin_mask
    if int(non_skin.sum()) < 1000:
        return _intraoral_wb(img)
    bgr_non_skin = img[non_skin]
    mean_bgr = bgr_non_skin.mean(axis=0)
    gray = mean_bgr.mean()
    gain = np.array([gray / max(mean_bgr[0], 1e-6),
                     gray / max(mean_bgr[1], 1e-6),
                     gray / max(mean_bgr[2], 1e-6)])
    corrected = _apply_gain(img, tuple(gain.tolist()))
    if int(skin_mask.sum()) > 1000:
        skin_lab_after = cv2.cvtColor(corrected, cv2.COLOR_BGR2LAB)
        a_after = (skin_lab_after[..., 1].astype(np.int16) - 128)[skin_mask].mean()
        b_after = (skin_lab_after[..., 2].astype(np.int16) - 128)[skin_mask].mean()
        delta = float(np.hypot(a_after - SKIN_ANCHOR_AB[0], b_after - SKIN_ANCHOR_AB[1]))
        if delta > SKIN_PROTECTION_THRESHOLD:
            damped = 1.0 + (gain - 1.0) * 0.5
            gain = damped
            corrected = _apply_gain(img, tuple(gain.tolist()))
    return WBResult(corrected, "portrait",
                    (float(gain[2]), float(gain[1]), float(gain[0])), 0.0,
                    "skin-protected gray-world")


def _polarized_wb(img: np.ndarray, case_median_ab):
    if case_median_ab is None:
        return WBResult(img.copy(), "polarized", (1.0, 1.0, 1.0), 0.0,
                        "trusted as-shot")
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    a_mean = float(lab[..., 1].astype(np.int16).mean() - 128)
    b_mean = float(lab[..., 2].astype(np.int16).mean() - 128)
    delta = float(np.hypot(a_mean - case_median_ab[0], b_mean - case_median_ab[1]))
    if delta < 8.0:
        return WBResult(img.copy(), "polarized", (1.0, 1.0, 1.0), 0.0,
                        f"within case median (ΔE={delta:.1f})")
    lab = lab.astype(np.float32)
    lab[..., 1] -= (a_mean - case_median_ab[0])
    lab[..., 2] -= (b_mean - case_median_ab[1])
    lab = np.clip(lab, 0, 255).astype(np.uint8)
    return WBResult(cv2.cvtColor(lab, cv2.COLOR_LAB2BGR), "polarized",
                    (1.0, 1.0, 1.0), delta * 50,
                    f"drift correction (ΔE={delta:.1f})")


def correct_wb(path: Path, classification: str, case_median_ab=None) -> WBResult:
    img = _read_image(path)
    if classification == "polarized":
        return _polarized_wb(img, case_median_ab)
    if classification == "portrait":
        return _portrait_wb(img)
    return _intraoral_wb(img)


def compute_polarized_median_ab(paths):
    if not paths:
        return None
    a_means, b_means = [], []
    for p in paths:
        try:
            img = _read_image(p)
        except Exception:
            continue
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        a_means.append(float(lab[..., 1].astype(np.int16).mean() - 128))
        b_means.append(float(lab[..., 2].astype(np.int16).mean() - 128))
    if not a_means:
        return None
    return float(np.median(a_means)), float(np.median(b_means))


# ---------------------------------------------------------------- crop

VIEW_ASPECT = {
    1: (4, 5), 2: (4, 5), 3: (4, 5),
    4: (3, 2), 5: (3, 2), 6: (3, 2),
    7: (3, 2), 8: (3, 2), 9: (3, 2), 10: (3, 2),
    11: (4, 3), 12: (4, 3),
    13: (1, 1),
}
OCCLUSAL_VIEWS = {11, 12}


def crop_to_aspect(img, target_w, target_h):
    h, w = img.shape[:2]
    target = target_w / target_h
    actual = w / h
    if actual > target:
        new_w = int(h * target)
        x0 = (w - new_w) // 2
        return img[:, x0:x0 + new_w]
    new_h = int(w / target)
    y0 = (h - new_h) // 2
    return img[y0:y0 + new_h, :]


def aacd_crop(img, view_number):
    if view_number not in VIEW_ASPECT:
        return img
    tw, th = VIEW_ASPECT[view_number]
    cropped = crop_to_aspect(img, tw, th)
    if view_number in OCCLUSAL_VIEWS:
        cropped = np.flipud(cropped).copy()
    return cropped


# ---------------------------------------------------------------- composite

BOARD_DPI = 300
BOARD_INCHES = (11.0, 8.5)
BOARD_MARGIN_IN = 0.5
BOARD_GAP_IN = 0.25
BOARD_GRID = (4, 3)
BOARD_BG = (255, 255, 255)
LABEL_FONT = cv2.FONT_HERSHEY_SIMPLEX
LABEL_COLOR = (40, 40, 40)
WATERMARK_TEXT = "Generated with Dental Photo Toolkit · Pablo Atria"


def fit_into(img, cell_w, cell_h, bg=(255, 255, 255)):
    h, w = img.shape[:2]
    scale = min(cell_w / w, cell_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.full((cell_h, cell_w, 3), bg, dtype=np.uint8)
    x0 = (cell_w - new_w) // 2
    y0 = (cell_h - new_h) // 2
    canvas[y0:y0 + new_h, x0:x0 + new_w] = resized
    return canvas


def before_after(before, after):
    h = max(before.shape[0], after.shape[0])
    target_aspect = max(before.shape[1] / before.shape[0],
                        after.shape[1] / after.shape[0])
    cell_w = int(h * target_aspect)
    cell_h = h
    left = fit_into(before, cell_w, cell_h)
    right = fit_into(after, cell_w, cell_h)
    gap = np.full((cell_h, 6, 3), 255, dtype=np.uint8)
    return np.hstack([left, gap, right])


def aacd_board(views, watermark=True):
    cols, rows = BOARD_GRID
    W = int(BOARD_INCHES[0] * BOARD_DPI)
    H = int(BOARD_INCHES[1] * BOARD_DPI)
    margin = int(BOARD_MARGIN_IN * BOARD_DPI)
    gap = int(BOARD_GAP_IN * BOARD_DPI)
    cell_w = (W - 2 * margin - (cols - 1) * gap) // cols
    cell_h = (H - 2 * margin - (rows - 1) * gap) // rows
    board = np.full((H, W, 3), BOARD_BG, dtype=np.uint8)
    for idx, view_num in enumerate(range(1, 13)):
        col = idx % cols
        row = idx // cols
        x0 = margin + col * (cell_w + gap)
        y0 = margin + row * (cell_h + gap)
        img = views.get(view_num)
        if img is None:
            placeholder = np.full((cell_h, cell_w, 3), (245, 245, 245), dtype=np.uint8)
            cv2.rectangle(placeholder, (0, 0), (cell_w - 1, cell_h - 1),
                          (200, 200, 200), 2)
            text = f"View {view_num} missing"
            (tw, th), _ = cv2.getTextSize(text, LABEL_FONT, 0.7, 1)
            cv2.putText(placeholder, text,
                        ((cell_w - tw) // 2, (cell_h + th) // 2),
                        LABEL_FONT, 0.7, (140, 140, 140), 1, cv2.LINE_AA)
            board[y0:y0 + cell_h, x0:x0 + cell_w] = placeholder
        else:
            board[y0:y0 + cell_h, x0:x0 + cell_w] = fit_into(img, cell_w, cell_h, BOARD_BG)
        cv2.putText(board, str(view_num),
                    (x0 + cell_w - 24, y0 + cell_h - 8),
                    LABEL_FONT, 0.5, LABEL_COLOR, 1, cv2.LINE_AA)
    if watermark:
        (tw, th), _ = cv2.getTextSize(WATERMARK_TEXT, LABEL_FONT, 0.4, 1)
        cv2.putText(board, WATERMARK_TEXT,
                    (W - margin - tw, H - margin // 3),
                    LABEL_FONT, 0.4, (160, 160, 160), 1, cv2.LINE_AA)
    return board


def write_image(img, out_path, jpeg_quality=95):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = out_path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        cv2.imwrite(str(out_path), img, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    elif suffix == ".png":
        cv2.imwrite(str(out_path), img, [cv2.IMWRITE_PNG_COMPRESSION, 4])
    else:
        cv2.imwrite(str(out_path), img)


# ---------------------------------------------------------------- orchestrator

PORTRAIT_VIEWS = {1, 2, 3, 4, 5, 6}


def _classify_for_wb(rec: PhotoRecord) -> str:
    if rec.polarization == "polarized":
        return "polarized"
    if rec.view_number in PORTRAIT_VIEWS:
        return "portrait"
    return "intraoral"


def _stem(rec: PhotoRecord) -> str:
    p = Path(rec.path)
    return f"{rec.timepoint}_v{rec.view_number:02d}_{rec.polarization}_{p.stem}"


def run_pipeline(case_folder: Path, work_dir: Path, watermark: bool = True) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    records = scan_case(case_folder)
    with open(work_dir / "manifest.csv", "w", newline="") as f:
        if records:
            writer = csv.DictWriter(f, fieldnames=list(asdict(records[0]).keys()))
            writer.writeheader()
            for r in records:
                writer.writerow(asdict(r))

    polarized_paths = [Path(r.path) for r in records if r.polarization == "polarized"]
    case_median_ab = compute_polarized_median_ab(polarized_paths) if polarized_paths else None

    wb_results = {}
    cropped = {}
    (work_dir / "wb").mkdir(exist_ok=True)
    (work_dir / "crops").mkdir(exist_ok=True)
    (work_dir / "before_after").mkdir(exist_ok=True)
    (work_dir / "boards").mkdir(exist_ok=True)

    for r in records:
        try:
            res = correct_wb(Path(r.path), _classify_for_wb(r), case_median_ab)
        except Exception as e:
            print(f"WB failed on {r.path}: {e}", file=sys.stderr)
            continue
        wb_results[r.path] = res
        write_image(res.image, work_dir / "wb" / f"{_stem(r)}.jpg")
        if r.view_number > 0:
            ci = aacd_crop(res.image, r.view_number)
            cropped[r.path] = ci
            write_image(ci, work_dir / "crops" / f"{_stem(r)}.jpg")

    before_by_view = {r.view_number: r for r in records
                      if r.timepoint == "before" and r.view_number > 0
                      and r.polarization == "non_polarized"}
    after_by_view = {r.view_number: r for r in records
                     if r.timepoint == "after" and r.view_number > 0
                     and r.polarization == "non_polarized"}
    for view in sorted(set(before_by_view) & set(after_by_view)):
        b_img = cropped.get(before_by_view[view].path) or wb_results[before_by_view[view].path].image
        a_img = cropped.get(after_by_view[view].path) or wb_results[after_by_view[view].path].image
        comp = before_after(b_img, a_img)
        write_image(comp, work_dir / "before_after" / f"v{view:02d}_before_after.jpg")

    for tp in ("before", "after"):
        tp_recs = [r for r in records if r.timepoint == tp and r.view_number > 0
                   and r.polarization == "non_polarized"]
        if not tp_recs:
            continue
        views = {r.view_number: cropped.get(r.path) or wb_results[r.path].image
                 for r in tp_recs}
        board = aacd_board(views, watermark=watermark)
        write_image(board, work_dir / "boards" / f"{tp}_aacd_board.png")

    by_tp = defaultdict(int)
    by_view = defaultdict(int)
    for r in records:
        by_tp[r.timepoint] += 1
        by_view[r.view_number] += 1
    with open(work_dir / "report.md", "w") as f:
        f.write(f"# Case Report — {case_folder.name}\n\n")
        f.write(f"Total images: {len(records)}\n\n## By timepoint\n")
        for tp, n in sorted(by_tp.items()):
            f.write(f"- {tp}: {n}\n")
        f.write("\n## By view\n")
        for v, n in sorted(by_view.items()):
            f.write(f"- View {v} ({VIEW_LABELS.get(v, 'unknown')}): {n}\n")


def zip_dir(src: Path, dest_zip: Path) -> None:
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in src.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(src))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_folder", type=Path)
    parser.add_argument("--output", type=Path, required=True,
                        help="Output ZIP path")
    parser.add_argument("--watermark", action="store_true", default=True)
    parser.add_argument("--no-watermark", dest="watermark", action="store_false")
    args = parser.parse_args()

    if not args.case_folder.exists():
        sys.exit(f"Case folder not found: {args.case_folder}")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "out"
        run_pipeline(args.case_folder, work, watermark=args.watermark)
        zip_dir(work, args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
```

**Step 4: Install pytest if missing, run the smoke test**

```bash
python3 -m pip install --quiet --user pytest
cd /Users/pabloatria/Downloads/photo-skill/dental-photo-toolkit-gpt
python3 -m pytest test_pipeline.py -v
```
Expected: PASS — pipeline runs end-to-end on the synthetic case, ZIP contains `aacd_board.png`, `before_after/`, `manifest.csv`, `report.md`.

**Step 5: Commit**

```bash
cd /Users/pabloatria/Downloads/photo-skill
git add dental-photo-toolkit-gpt/pipeline.py dental-photo-toolkit-gpt/test_pipeline.py
git commit -m "feat(gpt): single-file JPEG-only pipeline + smoke test"
```

---

## Task 3: Write the GPT system instructions

**Files:**
- Create: `dental-photo-toolkit-gpt/instructions.md`

**Step 1: Write `instructions.md`**

This is the system prompt Pablo pastes into the "Instructions" field when creating the GPT in ChatGPT.

```markdown
# Dental Photo Toolkit — System Instructions

You are the Dental Photo Toolkit, a focused tool by Dr. Pablo Atria that processes clinical dental photography. You produce white-balanced versions, AACD-standard crops, before/after composites, and the 12-photo AACD accreditation board from photos the user uploads.

## Your behavior

1. **Drop-and-go.** When the user uploads photos (or a ZIP), do not ask permission. Run the pipeline immediately. Time matters more than ceremony — clinicians are busy.
2. **Use Code Interpreter to run `pipeline.py`.** Save uploaded files to `/mnt/data/case/`, then run:
   ```
   python /mnt/data/pipeline.py /mnt/data/case --output /mnt/data/result.zip
   ```
   If a ZIP was uploaded, unzip it into `/mnt/data/case/` first.
3. **Surface the AACD board inline** as an image so the user sees the result immediately. Then offer the ZIP as a download.
4. **Summarize in one short paragraph**: how many photos detected, which views, what was missing, anything flagged. Use clinical language — concise, specific, no marketing phrasing.
5. **JPEG/PNG/TIFF only.** If the user uploads RAW (CR3, NEF, ARW, DNG, RW2, ORF), reply: "RAW files aren't supported in the GPT version. Export JPEG from your editor (Lightroom / Capture One / Photos) and re-upload. The Claude Code skill version of this tool handles RAW directly if needed."
6. **Filename conventions** are in your knowledge file `filename_conventions.md`. If files are unnamed or ambiguous and the manifest shows unresolved entries, do not guess — ask the user once which view each unnamed file represents, then re-run.
7. **AACD framing standards** are in `aacd_standards.md`. Reference them if the user asks about views, framing, or what's required for accreditation.
8. **Watermark.** The AACD board has a small "Generated with Dental Photo Toolkit · Pablo Atria" footer by default. If the user asks to remove it, re-run with `--no-watermark`.
9. **Tone.** Clinical, precise, English. No emoji. No marketing language. Match the voice of a senior clinician — confident, specific, no fluff.

## Constraints to communicate clearly when relevant

- File limits: < 20 MB per file, < 500 MB total, max 36 files per session.
- Minimum 8 of 12 views for an AACD board (placeholders fill the rest).
- Minimum one matched pre/post pair for a before/after composite.

## What you do NOT do

- Do not generate dental images. You process them, you don't create them.
- Do not provide clinical advice. You're a post-processing tool, not a diagnostic system.
- Do not search the web. All knowledge needed is in your bundled files.
- Do not engage with non-dental-photography requests. Politely redirect: "This tool processes dental clinical photography. Try the main ChatGPT for general questions."

## When something fails

If `pipeline.py` errors, surface the actual error message (don't paraphrase), and suggest: re-upload, check file format, check file size. Don't loop — escalate to the user after one retry.
```

**Step 2: Commit**

```bash
cd /Users/pabloatria/Downloads/photo-skill
git add dental-photo-toolkit-gpt/instructions.md
git commit -m "feat(gpt): system instructions"
```

---

## Task 4: Write the welcome message

**Files:**
- Create: `dental-photo-toolkit-gpt/welcome_message.md`

**Step 1: Write `welcome_message.md`**

This goes in the "Conversation starters" / first-message field in ChatGPT's GPT builder.

```markdown
# Welcome message (paste into "Description" or first-message field)

**Dental Photo Toolkit** — by Dr. Pablo Atria.

Drop a folder of clinical photos (JPEG, PNG, or TIFF — or one ZIP) and I'll return:

- White-balanced versions of every image
- AACD-standard crops by view
- Before / after composites for matched pre/post pairs
- The 12-photo AACD accreditation board (4 × 3, 300 dpi)
- A manifest CSV and a one-paragraph case report

## Upload guidelines

- **Format:** JPEG, PNG, or TIFF only. RAW (CR3 / NEF / ARW) → export JPEG first.
- **Size:** under 20 MB per file, under 500 MB total, up to 36 files per session.
- **Naming (auto-classification):** for example `pre_retracted_apart.jpg`, `post_face_smile.jpg`, `pre_occlusal_max.jpg`. Add `_pol` for polarized variants (e.g. `pre_retracted_apart_pol.jpg`).
- **For an AACD board:** at least 8 of the 12 standard views. Missing views render as labeled placeholders.
- **For a before/after:** at least one matched pre/post pair (same view name).

## Suggested starters

- "Process this case." (then drop the ZIP)
- "Build the AACD board from these 12 photos."
- "Make a before/after composite from these two."
- "What are the 12 AACD views?"

JPEG only. No external services. Free.
```

**Step 2: Commit**

```bash
cd /Users/pabloatria/Downloads/photo-skill
git add dental-photo-toolkit-gpt/welcome_message.md
git commit -m "feat(gpt): welcome message + user guidelines"
```

---

## Task 5: Adapt knowledge files from the Claude skill

**Files:**
- Create: `dental-photo-toolkit-gpt/knowledge/aacd_standards.md` (copy of skill's, lightly adapted)
- Create: `dental-photo-toolkit-gpt/knowledge/filename_conventions.md` (copy of skill's, lightly adapted)

**Step 1: Copy AACD standards**

```bash
cp /Users/pabloatria/Downloads/photo-skill/dental-photo-processor/references/aacd_photo_standards.md \
   /Users/pabloatria/Downloads/photo-skill/dental-photo-toolkit-gpt/knowledge/aacd_standards.md
```

**Step 2: Copy filename conventions**

```bash
cp /Users/pabloatria/Downloads/photo-skill/dental-photo-processor/references/filename_conventions.md \
   /Users/pabloatria/Downloads/photo-skill/dental-photo-toolkit-gpt/knowledge/filename_conventions.md
```

**Step 3: Verify**

```bash
ls /Users/pabloatria/Downloads/photo-skill/dental-photo-toolkit-gpt/knowledge/
```
Expected: `aacd_standards.md`, `filename_conventions.md`.

**Step 4: Commit**

```bash
cd /Users/pabloatria/Downloads/photo-skill
git add dental-photo-toolkit-gpt/knowledge/
git commit -m "feat(gpt): knowledge files (AACD standards, filename conventions)"
```

---

## Task 6: Write the publishing README

**Files:**
- Create: `dental-photo-toolkit-gpt/README.md`

**Step 1: Write `README.md`**

```markdown
# Dental Photo Toolkit — Custom GPT

Public Custom GPT companion to the `dental-photo-processor` Claude skill.
JPEG/PNG/TIFF only. Free. Branded as "Dr. Pablo Atria."

## Files in this folder

| File | Purpose |
|---|---|
| `pipeline.py` | Single-file Python pipeline. Upload as a knowledge file. |
| `instructions.md` | System prompt. Paste into the GPT's "Instructions" field. |
| `welcome_message.md` | First-message text + suggested conversation starters. |
| `knowledge/aacd_standards.md` | AACD 12-view reference. Upload as a knowledge file. |
| `knowledge/filename_conventions.md` | Filename → view mapping. Upload as a knowledge file. |
| `test_pipeline.py` | Local smoke test (not uploaded; run before publishing). |

## Pre-publish checklist

1. Run the smoke test once and confirm it passes:
   ```bash
   cd dental-photo-toolkit-gpt
   python3 -m pytest test_pipeline.py -v
   ```
2. Skim `instructions.md` for voice / accuracy.
3. Skim `welcome_message.md` for tone.

## Publishing to ChatGPT (10 minutes)

1. Open ChatGPT (Plus account required).
2. Sidebar → **Explore GPTs** → **+ Create**.
3. Switch to **Configure** tab.
4. Fill in:
   - **Name:** `Dental Photo Toolkit by Dr. Pablo Atria`
   - **Description:** "Process clinical dental photography in seconds — white balance, AACD-standard crops, before/after composites, and the 12-photo accreditation board. JPEG only. By Dr. Pablo Atria."
   - **Instructions:** paste the contents of `instructions.md`.
   - **Conversation starters:** paste the four starters from `welcome_message.md`.
   - **Knowledge:** upload `pipeline.py`, `knowledge/aacd_standards.md`, `knowledge/filename_conventions.md`.
   - **Capabilities:** **Code Interpreter ✅**, Web Browsing ❌, DALL-E ❌.
   - **Actions:** none.
5. **Profile picture / icon:** upload a minimal mark (placeholder icon OK for v1; design later).
6. **Privacy** for soft launch: **Anyone with the link**. Test with 2–3 real cases yourself + 2–3 colleagues.
7. After feedback round: switch to **GPT Store: Everyone**.

## Soft-launch test cases to try in your published GPT

1. Upload the synthetic test case from the Claude skill (`/tmp/dental_test_case` after running `_make_test_case.py`). Should produce a complete board.
2. Upload only 6 retracted views, no portraits. Should produce a board with 6 placeholders + a clear missing-views note.
3. Upload one matched before/after pair (e.g. `pre_retracted_apart.jpg` + `post_retracted_apart.jpg`). Should produce a 2-up composite, no full board.
4. Upload a CR3. Should refuse cleanly with the JPEG-only message.

## Future updates

To update the GPT after publishing, edit the files in this folder, commit, then in ChatGPT re-upload the changed files into the GPT's knowledge section. The Custom GPT does not auto-sync from your local files — it's a manual re-upload.
```

**Step 2: Commit**

```bash
cd /Users/pabloatria/Downloads/photo-skill
git add dental-photo-toolkit-gpt/README.md
git commit -m "docs(gpt): publishing checklist and soft-launch test cases"
```

---

## Task 7: Final verification — run the smoke test on a fresh checkout

**Files:**
- Touch: none. This is a verification pass.

**Step 1: Run the smoke test**

```bash
cd /Users/pabloatria/Downloads/photo-skill/dental-photo-toolkit-gpt
python3 -m pytest test_pipeline.py -v
```
Expected: PASS.

**Step 2: Inspect a board output manually**

```bash
python3 -c "
import subprocess, sys, tempfile
from pathlib import Path
from zipfile import ZipFile
ROOT = Path('/Users/pabloatria/Downloads/photo-skill')
SYNTH = ROOT / 'dental-photo-processor' / 'scripts' / '_make_test_case.py'
PIPELINE = ROOT / 'dental-photo-toolkit-gpt' / 'pipeline.py'
with tempfile.TemporaryDirectory() as tmp:
    case = Path(tmp) / 'case'
    out = Path(tmp) / 'out.zip'
    subprocess.run([sys.executable, str(SYNTH), str(case)], check=True)
    subprocess.run([sys.executable, str(PIPELINE), str(case), '--output', str(out)], check=True)
    with ZipFile(out) as z:
        for name in z.namelist():
            print(name)
        # extract one board
        z.extract('boards/before_aacd_board.png', '/tmp/gpt_inspect')
print('Board extracted to /tmp/gpt_inspect/boards/before_aacd_board.png')
"
```
Expected: list includes `boards/before_aacd_board.png`, `boards/after_aacd_board.png`, `before_after/v07_before_after.jpg`, etc. Open the extracted board and confirm the watermark is visible bottom-right.

**Step 3: Tag the milestone**

```bash
cd /Users/pabloatria/Downloads/photo-skill
git tag -a v0.1.0-gpt-ready -m "Dental Photo Toolkit GPT artifacts ready for ChatGPT publish"
git tag --list
```

**Step 4: Final commit (only if anything changed)**

```bash
git status
# if nothing to commit, skip the next line
git commit -am "chore: post-verification cleanup" 2>/dev/null || echo "nothing to commit"
```

---

## Done

The folder `dental-photo-toolkit-gpt/` now contains everything Pablo needs to publish the Custom GPT. He follows the README's "Publishing to ChatGPT" section. No further code work is required after this plan executes.

## Notes for whoever executes this

- The whole plan should take ~30 minutes if everything works first-try.
- Tasks 3, 4, 5, 6 are mostly content writing — read them once before writing to keep voice consistent.
- The biggest risk is Task 2 — verify the smoke test passes before moving on. If it fails, the most likely causes are import paths, missing test deps, or a typo in the merged code. Read the pytest output carefully; do not patch around symptoms.
- Voice and tone in `instructions.md` and `welcome_message.md` matter — Pablo cares about this. If anything reads as marketing-y or generic, rewrite. Reference his global CLAUDE.md preferences.
