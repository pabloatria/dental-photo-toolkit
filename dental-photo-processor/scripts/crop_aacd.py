"""AACD-standard crops per view.

Each AACD view has a target aspect ratio. We center-crop to that ratio. We do
NOT attempt subject detection — the assumption is the photographer framed
correctly at capture time and we're enforcing aspect consistency for the
board layout. If the original is mis-framed, no crop fixes it cleanly.

For occlusal views (11, 12), we also flip vertically per clinical convention
so anterior teeth appear at the top of the frame.
"""

from __future__ import annotations

import numpy as np

# Target aspect ratio (W:H) per view number
VIEW_ASPECT = {
    1:  (4, 5),    # full face smile — portrait
    2:  (4, 5),    # full face repose
    3:  (4, 5),    # profile
    4:  (3, 2),    # wide smile
    5:  (3, 2),    # right buccal smile
    6:  (3, 2),    # left buccal smile
    7:  (3, 2),    # retracted apart
    8:  (3, 2),    # retracted MIP
    9:  (3, 2),    # retracted right
    10: (3, 2),    # retracted left
    11: (4, 3),    # maxillary occlusal
    12: (4, 3),    # mandibular occlusal
    13: (1, 1),    # EAED 1:1 close-up
}

OCCLUSAL_VIEWS = {11, 12}


def crop_to_aspect(img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    h, w = img.shape[:2]
    target = target_w / target_h
    actual = w / h
    if actual > target:
        # too wide → crop horizontally
        new_w = int(h * target)
        x0 = (w - new_w) // 2
        return img[:, x0:x0 + new_w]
    # too tall → crop vertically
    new_h = int(w / target)
    y0 = (h - new_h) // 2
    return img[y0:y0 + new_h, :]


def aacd_crop(img: np.ndarray, view_number: int) -> np.ndarray:
    if view_number not in VIEW_ASPECT:
        return img
    target_w, target_h = VIEW_ASPECT[view_number]
    cropped = crop_to_aspect(img, target_w, target_h)
    if view_number in OCCLUSAL_VIEWS:
        cropped = np.flipud(cropped).copy()
    return cropped
