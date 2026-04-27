---
name: dental-photo-processor
description: Batch-processes intraoral and portrait dental photography for case documentation. Use whenever the user mentions processing dental photos, AACD or EAED accreditation photography, before/after composites, intraoral white balance, cross-polarized vs non-polarized shade matching, retracted views, occlusal mirror shots, the 12-photo accreditation board, or asks to clean up / standardize / crop / batch-edit a folder of dental images. Triggers even when the user says "fix these clinical photos", "make a before/after", "process this case", or just hands over a case folder. Handles RAW (CR3, NEF, ARW, DNG) and JPEG. Non-destructive.
---

# Dental Photo Processor

Automates post-processing for clinical dental photography. Pablo shoots cases at AS Odontología and NYU; this skill takes a raw case folder and produces white-balanced, standardized crops, paired before/after composites, and AACD/EAED-format 12-photo boards.

## When this skill should run

Triggered any time the user wants to:
- Clean up a case folder of intraoral or portrait shots
- Build before/after composites (2-up horizontal)
- Generate the AACD accreditation 12-photo board
- Fix white balance across mixed polarized / non-polarized shoots
- Standardize crops across a series for publication or social

If the user just says "process this case" or hands over a folder path, run the full pipeline.

## Why this exists

Clinical photography sits between art and evidence: it has to be aesthetically clean (presentation, social, publication) AND metrologically honest (shade decisions, longitudinal comparison). The most expensive mistake is publishing a case where white balance drifted between visits — the "after" looks better only because the camera saw it differently. This skill enforces consistency without flattening the image.

## Inputs

A **case folder**. Subfolder structure is flexible — the skill scans recursively. Common layouts that work out of the box:

```
PatientName_Date/
├── before/
│   ├── IMG_1234.CR3
│   ├── IMG_1234_pol.CR3
│   └── ...
└── after/
    └── ...
```

Or flat:
```
Case_2026-04-26/
├── pre_frontal_retracted.jpg
├── pre_frontal_retracted_pol.jpg
├── post_frontal_retracted.jpg
└── ...
```

The skill **reads filenames + EXIF** to classify each image by:

| Axis | Detected from |
|---|---|
| Timepoint (before / after) | Subfolder name OR filename prefix (`pre_`, `post_`, `before_`, `after_`, `antes_`, `despues_`) |
| Polarization | Filename suffix (`_pol`, `_xp`, `_cross` → polarized; default or `_np` → non-polarized) |
| AACD view type | Filename keywords (`frontal`, `lateral_right`, `occlusal_max`, `profile`, `smile`, `retracted`, `1to1`, etc.) |

If classification is ambiguous, the script writes a `manifest.csv` and stops, asking the user to fill in blanks. Re-run with `--manifest manifest.csv` to proceed.

## Workflow

Run the full pipeline:

```bash
python scripts/process_photos.py <case-folder>
```

Or step by step (useful for debugging or partial reruns):

```bash
python scripts/process_photos.py <case-folder> --steps wb,crop,compose,board
```

Available steps:
- `wb` — white balance correction (per-image, polarization-aware)
- `crop` — AACD-standard crops per view type
- `compose` — 2-up horizontal before/after pairs
- `board` — 12-photo AACD accreditation board
- `polar` — cross-polarized vs non-polarized side-by-side comparisons (when both exist)

Outputs land in `<case-folder>/_processed/`. Originals are never modified.

## White balance — no gray card present

Pablo doesn't currently shoot with a reference card. The skill uses a three-tier strategy, applied per-image based on classification:

1. **Cross-polarized shots** — Trust the camera's as-shot WB from EXIF. Cross-pol with controlled flash already removes most cast; aggressive auto-correction here introduces error rather than removing it. Apply correction only if a measured drift > 400 K is detected vs. the case median.

2. **Non-polarized intraoral** — Sample specular highlights on enamel as an internal neutral reference (the brightest near-neutral pixels in the upper percentiles), combined with a constrained gray-world fallback. Enamel highlights are the most reliable internal reference when no card is present, because they're effectively a partial mirror of the flash.

3. **Portraits / full-face** — Gray-world correction with skin-tone protection (an a*b* clamp around typical Mediterranean-to-fair skin chromaticity to prevent the algorithm from pushing faces magenta or green).

When you eventually shoot with a card, pass `--reference path/to/card_sample.jpg` and the skill will sample the gray patch directly. **Strong recommendation:** add an X-Rite ColorChecker Passport ($80) to your kit. It collapses this whole tier system into a one-line correction with publication-grade accuracy. The skill is built to take advantage of it the day you do.

See `references/white_balance_method.md` for the full algorithm and tunable parameters.

## Cross-polarization handling

When the same view is shot polarized AND non-polarized (standard practice for shade matching), the skill:

1. Pairs them by view + timestamp proximity (within 60 s).
2. Skips automatic WB on the polarized shot (per tier 1 above).
3. Generates a side-by-side comparison in `_processed/polarization/<view>.jpg`.
4. Flags shade-relevant views (anterior frontal, 1:1 close-up) for manual review.

If only one of the pair is present, the skill notes it in the manifest and processes singly.

## AACD 12-photo board

The board follows AACD Accreditation photographic requirements. See `references/aacd_photo_standards.md` for the full view list, framing rules, and the official AACD reference.

Output: a single high-resolution PNG (300 dpi, suitable for print and accreditation submission) at `_processed/aacd_board.png`. Missing views render as labeled placeholders and are listed in `_processed/report.md` so you know what's needed before submission.

## Before/after composites

For each timepoint pair, the skill produces a 2-up horizontal composite:
- Left: before, right: after
- Identical crop and aspect across both halves (forced consistency — the whole point of a comparison)
- Subtle hairline divider, no labels by default (clinical, not marketing)
- Optional `--label` flag adds minimal "Before / After" text in figure-legend style

Output: `_processed/before_after/<view>.jpg` per matched pair.

## Output structure

```
<case-folder>/_processed/
├── wb/                    # white-balanced versions of every input
├── crops/                 # AACD-standard crops by view
├── before_after/          # 2-up horizontal pairs
├── polarization/          # pol vs. non-pol comparisons
├── aacd_board.png         # 12-photo accreditation board
├── manifest.csv           # classification of every input
└── report.md              # summary, warnings, missing views
```

## Reference files

- `references/aacd_photo_standards.md` — the 12 required views, framing specs, official AACD reference
- `references/white_balance_method.md` — the three-tier algorithm, parameters, tuning notes
- `references/filename_conventions.md` — recognized filename keywords and how to override

## Scripts

- `scripts/process_photos.py` — main entry point, orchestrates the pipeline
- `scripts/white_balance.py` — per-image WB correction
- `scripts/classify.py` — filename + EXIF based view classification
- `scripts/crop_aacd.py` — AACD-standard crops
- `scripts/composite.py` — before/after and AACD board composites

## Dependencies

```
rawpy>=0.21       # RAW decoding (CR3, NEF, ARW, DNG)
numpy>=1.24
opencv-python>=4.8
Pillow>=10.0
exifread>=3.0
```

Install: `pip install -r requirements.txt`

## When the skill should hand off to the user

- Manifest classification has unknowns → present manifest.csv and ask user to fill in.
- AACD board missing 3+ views → ask whether to render with placeholders or wait for the missing shots.
- White balance correction exceeds 800 K shift on any image → flag for manual review (likely mis-set camera or mixed lighting).

Otherwise the skill should run end-to-end without prompting.
