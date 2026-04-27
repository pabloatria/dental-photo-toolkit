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
import sys
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

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
WATERMARK_TEXT = "Generated with Dental Photo Toolkit | Pablo Atria"


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
    if not records:
        print(f"No supported images found in {case_folder}", file=sys.stderr)
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
        b_path = before_by_view[view].path
        a_path = after_by_view[view].path
        b_img = cropped[b_path] if b_path in cropped else wb_results[b_path].image
        a_img = cropped[a_path] if a_path in cropped else wb_results[a_path].image
        comp = before_after(b_img, a_img)
        write_image(comp, work_dir / "before_after" / f"v{view:02d}_before_after.jpg")

    for tp in ("before", "after"):
        tp_recs = [r for r in records if r.timepoint == tp and r.view_number > 0
                   and r.polarization == "non_polarized"]
        if not tp_recs:
            continue
        views = {r.view_number: (cropped[r.path] if r.path in cropped
                                 else wb_results[r.path].image)
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
