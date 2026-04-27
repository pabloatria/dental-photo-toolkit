# AACD Photographic Documentation Standards

Reference for the 12-photograph accreditation series required by the American Academy of Cosmetic Dentistry. Pulled from the AACD Photographic Documentation Guide (current at time of writing — verify against the latest accreditation manual at aacd.com before final submission).

## The 12 required views

| # | View | Framing | Aspect | Notes |
|---|---|---|---|---|
| 1 | Full Face — Natural Smile | Lower 2/3 of face, eyes through chin | 4:5 portrait | Patient relaxed, posed natural smile, eyes open |
| 2 | Full Face — Repose | Same framing as #1 | 4:5 portrait | Lips at rest, no smile |
| 3 | Profile | Right profile, ear to chin tip | 4:5 portrait | Head in natural position (Frankfurt horizontal) |
| 4 | Wide Smile (1:2) | Tip of nose to chin, full smile | 3:2 landscape | Lips and teeth in frame, no skin beyond chin/nose |
| 5 | Right Buccal Smile | From right side, smile, posterior teeth visible | 3:2 landscape | Patient turns head, not camera angle |
| 6 | Left Buccal Smile | Mirror of #5 | 3:2 landscape | |
| 7 | Retracted Frontal — Teeth Apart | Maxillary and mandibular arches, ~3 mm gap | 3:2 landscape | Cheek retractors, midline centered |
| 8 | Retracted Frontal — Teeth Together | Same view, teeth in MIP | 3:2 landscape | |
| 9 | Retracted Right Lateral | Canine to last molar, right side | 3:2 landscape | Mirror or direct shot |
| 10 | Retracted Left Lateral | Mirror of #9 | 3:2 landscape | |
| 11 | Maxillary Occlusal | All maxillary teeth, mirror shot | 4:3 landscape | Occlusal mirror, no soft tissue beyond teeth dominant |
| 12 | Mandibular Occlusal | All mandibular teeth, mirror shot | 4:3 landscape | Tongue retracted |

## Framing rules

**Centering**
- All frontal views: dental midline aligned to image center within ±1% of width.
- Profile: eye and tragus on horizontal alignment line.
- Occlusal: arch curve centered top-to-bottom, midline vertical.

**Crop tightness**
- Full face: hair top excluded, chin to ~1 cm below.
- Smile views: 5–10% margin around lips.
- Retracted frontal: retractors edge-of-frame or just outside; teeth + 5 mm gingiva.
- Lateral retracted: canine to last visible molar with 5 mm gingival margin.
- Occlusal: full arch with second molars edge-of-frame, no excess palate/floor.

**Orientation**
- Occlusal mirror shots are flipped so anterior teeth appear at the **top** of the frame (clinical convention; the skill handles this automatically).
- Lateral shots are oriented with the patient's right on the **viewer's right** (anatomical convention, NOT mirrored).

## Color and exposure

AACD accepts a range but penalizes:
- Visible color cast across the series
- Inconsistent exposure (one image markedly darker/lighter than the rest)
- Specular blowouts on enamel that obscure incisal edge detail
- Missing or inconsistent retractor presence across the retracted views

The skill's WB and exposure normalization passes target consistency across the 12 — even if the absolute color is slightly off, drift between views is what loses points.

## Board layout

For accreditation submission, the 12 views are typically arranged in a 4×3 or 3×4 grid on a single board, white background, minimal labeling. The skill's default is 4 columns × 3 rows, in the order above (1–4 top row, 5–8 middle, 9–12 bottom).

Output specs:
- 300 dpi
- 11" × 8.5" landscape (33" × 25.5" at 300 dpi → 9900 × 7650 px)
- White background, 0.5" outer margin, 0.25" inter-image gap
- View number labels 8pt, bottom-right of each image (toggleable)

## EAED (European Academy of Esthetic Dentistry)

EAED accreditation overlaps heavily with AACD but differs in:
- Adds a maxillary anterior 1:1 close-up (frontal, retracted, central incisors filling frame)
- Allows 14-photo series (adds 1:1 and a "natural lighting" full-face)
- Color profile expectations are slightly stricter; cross-polarized images often required for restorative submissions

Pass `--standard eaed` to the script to switch to the EAED layout. The extra views are pulled from the same case folder if present.

## Filename keywords the classifier recognizes

```
frontal, frente              → views 1, 2, 7, 8 (depending on retracted/repose)
profile, perfil              → view 3
smile_wide, sonrisa_amplia   → view 4
right, derecha, der          → views 5 or 9 (smile vs retracted)
left, izquierda, izq         → views 6 or 10
retracted, retraido          → views 7, 8, 9, 10
occlusal_max, oclusal_sup    → view 11
occlusal_mand, oclusal_inf   → view 12
1to1, oneone, close          → EAED 1:1 close-up
repose, reposo               → view 2
teeth_apart, abierta         → view 7
teeth_together, mip          → view 8
```

Combine with `_pol` / `_xp` for polarized variants.
