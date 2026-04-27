# White Balance Method

Detailed algorithm and tunable parameters for the three-tier WB strategy in `scripts/white_balance.py`.

## Tier 1 — Cross-polarized shots

Cross-polarization with controlled flash produces an image where the dominant illuminant is the flash itself, filtered to remove the specular component. The remaining diffuse signal closely reflects true tissue/restoration color.

**Action**: read camera as-shot WB from EXIF (`WhiteBalance`, `ColorTemperature`, `Tint`). Apply if present. Do not auto-correct unless drift is detected.

**Drift detection**: compute the median Lab a*b* of all polarized shots in the case. Any image deviating > 8 ΔE from the median triggers a flag (likely camera mis-set on that frame). Apply correction only to flagged frames, pulling them toward the case median.

**Why not auto-correct uniformly**: aggressive gray-world on cross-pol shots removes the (correctly captured) chromatic information of the tissue itself. The image looks "more neutral" but is actually less accurate.

## Tier 2 — Non-polarized intraoral

Intraoral non-polarized shots have specular highlights on enamel that act as a near-mirror of the flash. These highlights, sampled correctly, give a robust internal neutral reference.

**Algorithm**:
1. Convert to Lab.
2. Identify candidate specular pixels: top 1% L*, |a*| < 5, |b*| < 5.
3. Reject if fewer than 1000 such pixels (image likely has no clear highlights — fall back to step 5).
4. Compute mean RGB of candidate pixels. Normalize so the mean equals neutral gray (R=G=B). Apply gain to whole image.
5. Fallback: constrained gray-world. Compute global mean RGB excluding the top 0.1% (specular blowouts) and bottom 5% (shadows). Normalize, then dampen the correction by 60% to avoid overcorrection on color-dominated scenes (gingiva-heavy).

**Tunable parameters** (in `scripts/white_balance.py`):
- `SPECULAR_PERCENTILE = 99` — luminance threshold for highlight sampling
- `SPECULAR_AB_TOLERANCE = 5` — a*b* range for "near-neutral"
- `MIN_SPECULAR_PIXELS = 1000` — fallback threshold
- `GRAYWORLD_DAMPING = 0.6` — softens fallback correction

## Tier 3 — Portraits / full-face

Faces dominate the frame; gray-world is reasonable but blind to skin tone. We add a chromaticity guardrail.

**Algorithm**:
1. Detect skin region (simple Lab range: L 30–80, a 5–25, b 10–35 — broad enough for fair-to-medium skin).
2. Compute gray-world correction on the **non-skin** region only.
3. Apply correction.
4. Re-check skin region a*b* — if it has shifted more than 6 ΔE from a "healthy skin" anchor (a≈15, b≈18), back off the correction by 50%.

**Why**: gray-world without protection turns warm-skinned patients magenta or green, depending on the dominant non-skin color (e.g., a blue clinic backdrop forces the correction warm, pushing skin orange).

## Drift report

After processing, the skill writes a `wb_report.csv` listing per-image:
- Detected color temperature (estimated from final neutral assumption)
- Tier applied
- Correction magnitude (ΔK and Δtint)
- Flag if > 800 K or > 15 magenta/green tint

Images flagged here should be reviewed manually. They often indicate a camera setting that drifted between shots — useful diagnostic for the photographer.

## When the user adds a gray card

If `--reference path/to/sample.jpg` is passed, the skill assumes the image contains a gray card / ColorChecker patch. It opens an interactive picker (or reads a `--patch x,y,w,h` flag) to sample the patch, computes the correction matrix from that single sample, and applies it to **every image in the case**.

This bypasses all three tiers and is the highest-accuracy mode. Recommend this workflow once a card is in the kit.
