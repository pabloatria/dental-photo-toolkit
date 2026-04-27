# Filename Conventions

The classifier in `scripts/classify.py` reads filenames (case-insensitive) to determine timepoint, polarization, and AACD view. Multiple keywords can combine.

## Timepoint

| Keyword | Meaning |
|---|---|
| `pre`, `before`, `antes`, `inicial`, `initial` | Before |
| `post`, `after`, `despues`, `final` | After |
| `intra`, `prov`, `provisional` | Intermediate (skipped from before/after pairs by default) |

Subfolder names take precedence over filename hints (a file in `before/` is "before" even if the filename says `post_`).

## Polarization

| Keyword | Meaning |
|---|---|
| `_pol`, `_xp`, `_cross`, `_polar`, `_xpl` | Polarized |
| `_np`, `_nopol`, `_normal` (or no marker) | Non-polarized |

## AACD views

| Keyword(s) | View # | Description |
|---|---|---|
| `face_smile`, `fullface_smile`, `cara_sonrisa` | 1 | Full face natural smile |
| `face_repose`, `fullface_repose`, `cara_reposo` | 2 | Full face repose |
| `profile`, `perfil` | 3 | Profile |
| `smile_wide`, `sonrisa_amplia`, `wide_smile` | 4 | Wide smile 1:2 |
| `right_smile`, `derecha_sonrisa`, `buccal_right` | 5 | Right buccal smile |
| `left_smile`, `izquierda_sonrisa`, `buccal_left` | 6 | Left buccal smile |
| `retracted_apart`, `frontal_apart`, `abierta` | 7 | Retracted, teeth apart |
| `retracted_mip`, `frontal_together`, `mip` | 8 | Retracted, teeth together |
| `retracted_right`, `lateral_right`, `lat_der` | 9 | Retracted right |
| `retracted_left`, `lateral_left`, `lat_izq` | 10 | Retracted left |
| `occlusal_max`, `oclusal_sup`, `upper_occlusal` | 11 | Maxillary occlusal |
| `occlusal_mand`, `oclusal_inf`, `lower_occlusal` | 12 | Mandibular occlusal |
| `1to1`, `oneone`, `close_anterior` | EAED bonus | 1:1 close-up anterior |

## Manifest override

If filenames don't match any pattern, the file is recorded with `view = unknown` in `manifest.csv`. Edit the CSV to fill in the view, then rerun:

```bash
python scripts/process_photos.py <case-folder> --manifest <case-folder>/_processed/manifest.csv
```

The manifest is the source of truth on the second run — the classifier is bypassed.

## Recommended convention going forward

For zero-classification-effort processing, name files like:

```
<patientID>_<timepoint>_<view>[_pol].<ext>
```

Examples:
```
PA1042_pre_retracted_apart.CR3
PA1042_pre_retracted_apart_pol.CR3
PA1042_post_occlusal_max.CR3
PA1042_post_face_smile.CR3
```

Or use subfolders for timepoint and just the view + pol marker in the filename:

```
PA1042_2026-04-26/
├── pre/
│   ├── retracted_apart.CR3
│   ├── retracted_apart_pol.CR3
│   └── occlusal_max.CR3
└── post/
    └── ...
```

Both layouts classify in one pass, no manifest editing needed.
