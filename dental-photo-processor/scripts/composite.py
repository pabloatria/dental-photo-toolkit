"""Composites: 2-up before/after pairs and the 12-photo AACD accreditation board.

Design philosophy: clinical, not marketing. White background, hairline dividers,
labels off by default, deterministic layout. The board mirrors the AACD
accreditation submission format (4×3 landscape, view-numbered cells).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# Layout constants — see references/aacd_photo_standards.md
BOARD_DPI = 300
BOARD_INCHES = (11.0, 8.5)            # landscape letter
BOARD_MARGIN_IN = 0.5
BOARD_GAP_IN = 0.25
BOARD_GRID = (4, 3)                   # cols × rows
BOARD_BG = (255, 255, 255)            # white

BEFORE_AFTER_GAP_PX = 6
BEFORE_AFTER_BG = (255, 255, 255)
LABEL_FONT = cv2.FONT_HERSHEY_SIMPLEX
LABEL_COLOR = (40, 40, 40)


def fit_into(img: np.ndarray, cell_w: int, cell_h: int,
             bg: tuple[int, int, int] = (255, 255, 255)) -> np.ndarray:
    """Resize img into cell preserving aspect, pad with bg."""
    h, w = img.shape[:2]
    scale = min(cell_w / w, cell_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.full((cell_h, cell_w, 3), bg, dtype=np.uint8)
    x0 = (cell_w - new_w) // 2
    y0 = (cell_h - new_h) // 2
    canvas[y0:y0 + new_h, x0:x0 + new_w] = resized
    return canvas


def before_after(before: np.ndarray, after: np.ndarray, *,
                 label: bool = False) -> np.ndarray:
    """2-up horizontal composite with identical cell size."""
    h = max(before.shape[0], after.shape[0])
    target_aspect = max(before.shape[1] / before.shape[0],
                        after.shape[1] / after.shape[0])
    cell_w = int(h * target_aspect)
    cell_h = h
    left = fit_into(before, cell_w, cell_h, BEFORE_AFTER_BG)
    right = fit_into(after, cell_w, cell_h, BEFORE_AFTER_BG)
    gap = np.full((cell_h, BEFORE_AFTER_GAP_PX, 3), BEFORE_AFTER_BG, dtype=np.uint8)
    composite = np.hstack([left, gap, right])

    if label:
        # figure-legend style: small, lower-left of each panel
        scale = max(cell_h / 800.0, 0.6)
        thickness = max(int(scale * 1.5), 1)
        cv2.putText(composite, "Before",
                    (int(cell_w * 0.03), cell_h - int(cell_h * 0.03)),
                    LABEL_FONT, scale, LABEL_COLOR, thickness, cv2.LINE_AA)
        cv2.putText(composite, "After",
                    (cell_w + BEFORE_AFTER_GAP_PX + int(cell_w * 0.03),
                     cell_h - int(cell_h * 0.03)),
                    LABEL_FONT, scale, LABEL_COLOR, thickness, cv2.LINE_AA)
    return composite


def aacd_board(views: dict[int, Optional[np.ndarray]], *,
               number_labels: bool = True,
               standard: str = "aacd") -> np.ndarray:
    """Produce the 12-cell board.

    `views` maps view_number → image (or None for missing). For EAED,
    pass standard="eaed" and include view 13; the board switches to 4×4
    or 5×3 to fit (we use 5×3 here to keep landscape orientation).
    """
    if standard == "eaed":
        cols, rows = 5, 3
        view_order = list(range(1, 14)) + [None, None]
    else:
        cols, rows = BOARD_GRID
        view_order = list(range(1, 13))

    W = int(BOARD_INCHES[0] * BOARD_DPI)
    H = int(BOARD_INCHES[1] * BOARD_DPI)
    margin = int(BOARD_MARGIN_IN * BOARD_DPI)
    gap = int(BOARD_GAP_IN * BOARD_DPI)

    cell_w = (W - 2 * margin - (cols - 1) * gap) // cols
    cell_h = (H - 2 * margin - (rows - 1) * gap) // rows

    board = np.full((H, W, 3), BOARD_BG, dtype=np.uint8)

    for idx, view_num in enumerate(view_order):
        col = idx % cols
        row = idx // cols
        x0 = margin + col * (cell_w + gap)
        y0 = margin + row * (cell_h + gap)
        if view_num is None:
            continue
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

        if number_labels:
            label = str(view_num)
            cv2.putText(board, label,
                        (x0 + cell_w - 24, y0 + cell_h - 8),
                        LABEL_FONT, 0.5, LABEL_COLOR, 1, cv2.LINE_AA)
    return board


def write_image(img: np.ndarray, out_path: Path, *, jpeg_quality: int = 95) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = out_path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        cv2.imwrite(str(out_path), img, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    elif suffix == ".png":
        cv2.imwrite(str(out_path), img, [cv2.IMWRITE_PNG_COMPRESSION, 4])
    else:
        cv2.imwrite(str(out_path), img)
