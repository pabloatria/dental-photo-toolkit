"""Three-tier white balance correction for dental photography.

See references/white_balance_method.md for the algorithm rationale.
The tiers are:
  1. Cross-polarized: trust EXIF, correct only on case-median drift.
  2. Non-polarized intraoral: enamel highlight sampling + damped gray-world fallback.
  3. Portrait/full-face: gray-world with skin-tone protection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

# Tunable parameters — see references/white_balance_method.md
SPECULAR_PERCENTILE = 99
SPECULAR_AB_TOLERANCE = 5
MIN_SPECULAR_PIXELS = 1000
GRAYWORLD_DAMPING = 0.6
SKIN_LAB_RANGE = ((30, 5, 10), (80, 25, 35))   # (Lmin,amin,bmin)-(Lmax,amax,bmax)
SKIN_ANCHOR_AB = (15.0, 18.0)
SKIN_PROTECTION_THRESHOLD = 6.0  # ΔE in a*b*

# Decompression-bomb cap. Covers any clinical DSLR/mirrorless sensor (~50 MP)
# with headroom; rejects crafted images claiming dimensions designed to OOM.
MAX_PIXELS = 80_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass
class WBResult:
    image: np.ndarray            # BGR uint8 corrected image
    tier: str                    # "polarized" | "intraoral" | "portrait"
    gain_rgb: tuple[float, float, float]
    correction_magnitude: float  # rough ΔK estimate (signed: + warmer, - cooler)
    notes: str = ""


def _read_image(path: Path) -> np.ndarray:
    """Read JPEG/PNG/TIF or RAW into BGR uint8 (8-bit working space)."""
    suffix = path.suffix.lower()
    if suffix in {".cr3", ".cr2", ".nef", ".arw", ".dng", ".raf", ".rw2", ".orf"}:
        # RAW path: rawpy decodes from camera sensor data, not a compressed
        # container — decompression bombs aren't a vector here. Trust the file.
        try:
            import rawpy
        except ImportError as e:
            raise RuntimeError(
                "rawpy is required to read RAW files. Install with: pip install rawpy"
            ) from e
        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(
                use_camera_wb=True,
                output_bps=8,
                no_auto_bright=False,
                gamma=(2.222, 4.5),
            )
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    # Compressed path (JPEG/PNG/TIFF): probe header dimensions before decoding.
    # Refuses decompression bombs before OpenCV allocates the frame buffer.
    # Restrict Pillow's auto-dispatch to formats we actually use — blocks
    # PSD/FITS code paths that have had bomb CVEs.
    try:
        with Image.open(path, formats=("JPEG", "PNG", "TIFF")) as probe:
            w, h = probe.size
    except Exception as e:
        raise RuntimeError(f"Could not read image header {path}: {e}")
    if w * h > MAX_PIXELS:
        raise RuntimeError(
            f"Image too large: {w}x{h} ({w*h:,} px > {MAX_PIXELS:,} px cap) — {path.name}"
        )
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Could not read {path}")
    return img


def _apply_gain(img: np.ndarray, gain_bgr: tuple[float, float, float]) -> np.ndarray:
    out = img.astype(np.float32)
    out[..., 0] *= gain_bgr[0]
    out[..., 1] *= gain_bgr[1]
    out[..., 2] *= gain_bgr[2]
    return np.clip(out, 0, 255).astype(np.uint8)


def _estimate_temperature_shift(gain_rgb: tuple[float, float, float]) -> float:
    """Rough sign+magnitude estimate of WB shift in Kelvin-equivalent.

    Positive = warmer correction (boosted red, cut blue). Used only as a
    diagnostic, not a calibrated measurement.
    """
    r, _, b = gain_rgb
    rb_ratio = r / max(b, 1e-6)
    return float((rb_ratio - 1.0) * 1500.0)


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
        sample = img[mask]  # BGR samples of specular highlights
        mean_bgr = sample.mean(axis=0)
        gray = mean_bgr.mean()
        gain = (gray / max(mean_bgr[0], 1e-6),
                gray / max(mean_bgr[1], 1e-6),
                gray / max(mean_bgr[2], 1e-6))
        corrected = _apply_gain(img, gain)
        gain_rgb = (gain[2], gain[1], gain[0])
        return WBResult(corrected, "intraoral",
                        gain_rgb, _estimate_temperature_shift(gain_rgb),
                        notes="enamel-highlight sampling")

    # fallback — damped gray-world
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
    corrected = _apply_gain(img, gain)
    gain_rgb = (gain[2], gain[1], gain[0])
    return WBResult(corrected, "intraoral",
                    gain_rgb, _estimate_temperature_shift(gain_rgb),
                    notes="damped gray-world (insufficient highlights)")


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
        # whole image is skin — fall back to mild damped gray-world
        return _intraoral_wb(img)

    bgr_non_skin = img[non_skin]
    mean_bgr = bgr_non_skin.mean(axis=0)
    gray = mean_bgr.mean()
    gain = np.array([gray / max(mean_bgr[0], 1e-6),
                     gray / max(mean_bgr[1], 1e-6),
                     gray / max(mean_bgr[2], 1e-6)])
    corrected = _apply_gain(img, tuple(gain.tolist()))

    # check skin chromaticity didn't drift
    if int(skin_mask.sum()) > 1000:
        skin_lab_after = cv2.cvtColor(corrected, cv2.COLOR_BGR2LAB)
        a_after = (skin_lab_after[..., 1].astype(np.int16) - 128)[skin_mask].mean()
        b_after = (skin_lab_after[..., 2].astype(np.int16) - 128)[skin_mask].mean()
        delta = float(np.hypot(a_after - SKIN_ANCHOR_AB[0], b_after - SKIN_ANCHOR_AB[1]))
        if delta > SKIN_PROTECTION_THRESHOLD:
            damped = 1.0 + (gain - 1.0) * 0.5
            gain = damped
            corrected = _apply_gain(img, tuple(gain.tolist()))

    gain_rgb = (float(gain[2]), float(gain[1]), float(gain[0]))
    return WBResult(corrected, "portrait", gain_rgb,
                    _estimate_temperature_shift(gain_rgb),
                    notes="skin-protected gray-world")


def _polarized_wb(img: np.ndarray, case_median_ab: Optional[tuple[float, float]]) -> WBResult:
    """Trust the camera. Correct only if this frame deviates from the case median."""
    if case_median_ab is None:
        return WBResult(img.copy(), "polarized", (1.0, 1.0, 1.0), 0.0,
                        notes="EXIF as-shot WB trusted")
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    a_mean = float(lab[..., 1].astype(np.int16).mean() - 128)
    b_mean = float(lab[..., 2].astype(np.int16).mean() - 128)
    delta = float(np.hypot(a_mean - case_median_ab[0], b_mean - case_median_ab[1]))
    if delta < 8.0:
        return WBResult(img.copy(), "polarized", (1.0, 1.0, 1.0), 0.0,
                        notes=f"within case median (ΔE={delta:.1f})")
    # Apply a corrective shift toward the case median in Lab.
    lab = lab.astype(np.float32)
    lab[..., 1] -= (a_mean - case_median_ab[0])
    lab[..., 2] -= (b_mean - case_median_ab[1])
    lab = np.clip(lab, 0, 255).astype(np.uint8)
    corrected = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    return WBResult(corrected, "polarized", (1.0, 1.0, 1.0), delta * 50,
                    notes=f"drift correction toward case median (ΔE={delta:.1f})")


def correct(path: Path, classification: str,
            case_median_ab: Optional[tuple[float, float]] = None) -> WBResult:
    """Public entry. classification ∈ {'polarized', 'intraoral', 'portrait'}."""
    img = _read_image(path)
    if classification == "polarized":
        return _polarized_wb(img, case_median_ab)
    if classification == "portrait":
        return _portrait_wb(img)
    return _intraoral_wb(img)


def compute_polarized_median_ab(paths: list[Path]) -> Optional[tuple[float, float]]:
    """Used by the orchestrator to derive the case-median chromaticity for tier 1."""
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
