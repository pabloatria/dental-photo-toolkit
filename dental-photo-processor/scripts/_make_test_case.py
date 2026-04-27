"""Generate a synthetic case folder for end-to-end testing.

Produces realistic-aspect dental-photo stand-ins with deliberate WB shifts and
the right filenames so the classifier picks them up. Not anatomically accurate
— this validates the pipeline plumbing, not clinical fidelity.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def _gradient(h: int, w: int, base_bgr: tuple[int, int, int]) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for c in range(3):
        col = np.linspace(base_bgr[c] * 0.7, min(base_bgr[c] * 1.3, 255), w)
        img[:, :, c] = np.tile(col, (h, 1)).astype(np.uint8)
    # add some specular-like highlights for the intraoral WB tier to grab
    rng = np.random.default_rng(0)
    for _ in range(40):
        cy, cx = rng.integers(h // 4, 3 * h // 4), rng.integers(w // 4, 3 * w // 4)
        cv2.circle(img, (cx, cy), rng.integers(4, 12), (250, 250, 250), -1)
    return img


def _apply_cast(img: np.ndarray, cast: tuple[float, float, float]) -> np.ndarray:
    out = img.astype(np.float32)
    out[..., 0] *= cast[0]
    out[..., 1] *= cast[1]
    out[..., 2] *= cast[2]
    return np.clip(out, 0, 255).astype(np.uint8)


VIEWS = [
    # (filename, aspect WxH, base BGR, view kind)
    ("face_smile",       (1200, 1500), (180, 175, 195), "portrait"),
    ("face_repose",      (1200, 1500), (180, 175, 195), "portrait"),
    ("profile",          (1200, 1500), (180, 175, 195), "portrait"),
    ("smile_wide",       (1800, 1200), (190, 170, 175), "portrait"),
    ("right_smile",      (1800, 1200), (190, 170, 175), "portrait"),
    ("left_smile",       (1800, 1200), (190, 170, 175), "portrait"),
    ("retracted_apart",  (1800, 1200), (200, 195, 230), "intraoral"),
    ("retracted_mip",    (1800, 1200), (200, 195, 230), "intraoral"),
    ("retracted_right",  (1800, 1200), (200, 195, 230), "intraoral"),
    ("retracted_left",   (1800, 1200), (200, 195, 230), "intraoral"),
    ("occlusal_max",     (1600, 1200), (200, 195, 230), "intraoral"),
    ("occlusal_mand",    (1600, 1200), (200, 195, 230), "intraoral"),
]

# deliberate per-timepoint cast — "before" cooler, "after" warmer
CASTS = {
    "pre":  (1.10, 1.00, 0.90),    # B↑ R↓ → cool
    "post": (0.92, 1.00, 1.12),    # B↓ R↑ → warm
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--with-pol", action="store_true",
                        help="Also emit polarized variants for retracted views")
    args = parser.parse_args()

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    for tp in ("pre", "post"):
        sub = out / tp
        sub.mkdir(exist_ok=True)
        for name, (w, h), base, kind in VIEWS:
            img = _gradient(h, w, base)
            img = _apply_cast(img, CASTS[tp])
            cv2.imwrite(str(sub / f"{name}.jpg"), img,
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
            if args.with_pol and kind == "intraoral":
                # polarized variant: less specular, slightly different cast
                pol = _gradient(h, w, base)
                pol = _apply_cast(pol, (1.0, 1.0, 1.0))  # neutral as-shot
                cv2.imwrite(str(sub / f"{name}_pol.jpg"), pol,
                            [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"Wrote synthetic case to {out}")


if __name__ == "__main__":
    main()
