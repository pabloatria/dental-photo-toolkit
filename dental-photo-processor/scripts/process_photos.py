"""Orchestrator: scans a case folder and runs the full pipeline.

Usage:
    python scripts/process_photos.py <case-folder>
    python scripts/process_photos.py <case-folder> --steps wb,crop,compose,board
    python scripts/process_photos.py <case-folder> --manifest <path>
    python scripts/process_photos.py <case-folder> --standard eaed --label

Outputs land in <case-folder>/_processed/. Originals are never modified.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent))

import classify
import composite
import crop_aacd
import white_balance


PORTRAIT_VIEWS = {1, 2, 3, 4, 5, 6}     # face/smile views — Tier 3
INTRAORAL_VIEWS = {7, 8, 9, 10, 11, 12, 13}  # retracted/occlusal — Tier 2 (or Tier 1 if pol)


def _classification_for_wb(record: classify.PhotoRecord) -> str:
    if record.polarization == "polarized":
        return "polarized"
    if record.view_number in PORTRAIT_VIEWS:
        return "portrait"
    return "intraoral"


def _safe_stem(record: classify.PhotoRecord) -> str:
    """Stable, human-readable stem for output filenames."""
    p = Path(record.path)
    parts = [record.timepoint, f"v{record.view_number:02d}", record.polarization, p.stem]
    return "_".join(parts)


def run(case_folder: Path, *, steps: set[str], manifest_path: Path | None,
        standard: str, label_composites: bool) -> None:
    out_root = case_folder / "_processed"
    out_root.mkdir(parents=True, exist_ok=True)

    # 1. Classify or read manifest
    if manifest_path and manifest_path.exists():
        records = classify.read_manifest(manifest_path)
        print(f"Loaded {len(records)} records from {manifest_path}")
    else:
        records = classify.scan_case(case_folder)
        manifest_out = out_root / "manifest.csv"
        classify.write_manifest(records, manifest_out)
        print(f"Classified {len(records)} images → {manifest_out}")
        if classify.has_unresolved(records):
            print("  Some images have unresolved timepoint/view.")
            print(f"  Edit {manifest_out} and rerun with --manifest {manifest_out}")
            return

    # 2. White balance
    wb_results: dict[str, white_balance.WBResult] = {}
    polarized_paths = [Path(r.path) for r in records if r.polarization == "polarized"]
    case_median_ab = white_balance.compute_polarized_median_ab(polarized_paths) \
        if polarized_paths else None

    if "wb" in steps:
        print("Running white balance pass...")
        wb_dir = out_root / "wb"
        wb_dir.mkdir(parents=True, exist_ok=True)
        wb_report_rows = []
        for r in records:
            tier = _classification_for_wb(r)
            try:
                result = white_balance.correct(Path(r.path), tier, case_median_ab)
            except Exception as e:
                print(f"  ! WB failed on {r.path}: {e}")
                continue
            wb_results[r.path] = result
            out_path = wb_dir / f"{_safe_stem(r)}.jpg"
            composite.write_image(result.image, out_path)
            wb_report_rows.append({
                "file": r.path,
                "tier": result.tier,
                "gain_r": f"{result.gain_rgb[0]:.3f}",
                "gain_g": f"{result.gain_rgb[1]:.3f}",
                "gain_b": f"{result.gain_rgb[2]:.3f}",
                "delta_k_estimate": f"{result.correction_magnitude:.0f}",
                "notes": result.notes,
                "flagged": "yes" if abs(result.correction_magnitude) > 800 else "",
            })
        with open(out_root / "wb_report.csv", "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["file", "tier", "gain_r", "gain_g", "gain_b",
                               "delta_k_estimate", "notes", "flagged"])
            writer.writeheader()
            writer.writerows(wb_report_rows)
        print(f"  Wrote {len(wb_report_rows)} WB-corrected images. Report → wb_report.csv")

    # 3. AACD crops
    cropped: dict[str, "object"] = {}  # path -> ndarray
    if "crop" in steps:
        print("Running AACD crop pass...")
        crop_dir = out_root / "crops"
        crop_dir.mkdir(parents=True, exist_ok=True)
        for r in records:
            if r.view_number == 0:
                continue
            src_img = (wb_results[r.path].image
                       if r.path in wb_results
                       else white_balance._read_image(Path(r.path)))
            cropped_img = crop_aacd.aacd_crop(src_img, r.view_number)
            cropped[r.path] = cropped_img
            out_path = crop_dir / f"{_safe_stem(r)}.jpg"
            composite.write_image(cropped_img, out_path)
        print(f"  Wrote {len(cropped)} cropped images.")

    # 4. Polarization comparisons
    if "polar" in steps:
        print("Building polarization comparisons...")
        pol_dir = out_root / "polarization"
        pol_dir.mkdir(parents=True, exist_ok=True)
        # group by (timepoint, view)
        pairs = defaultdict(dict)  # (tp, view) -> {"polarized": rec, "non_polarized": rec}
        for r in records:
            if r.view_number == 0 or r.timepoint == "unknown":
                continue
            pairs[(r.timepoint, r.view_number)][r.polarization] = r
        n = 0
        for (tp, view), bucket in pairs.items():
            if "polarized" not in bucket or "non_polarized" not in bucket:
                continue
            pol_rec = bucket["polarized"]
            np_rec = bucket["non_polarized"]
            np_img = (wb_results[np_rec.path].image
                      if np_rec.path in wb_results
                      else white_balance._read_image(Path(np_rec.path)))
            pol_img = (wb_results[pol_rec.path].image
                       if pol_rec.path in wb_results
                       else white_balance._read_image(Path(pol_rec.path)))
            comp = composite.before_after(np_img, pol_img, label=False)
            out_path = pol_dir / f"{tp}_v{view:02d}_np_vs_pol.jpg"
            composite.write_image(comp, out_path)
            n += 1
        print(f"  Wrote {n} polarization comparisons.")

    # 5. Before/after composites
    if "compose" in steps:
        print("Building before/after composites...")
        ba_dir = out_root / "before_after"
        ba_dir.mkdir(parents=True, exist_ok=True)
        # match by view, prefer non-polarized for the composite (clinical standard)
        before_by_view = {r.view_number: r for r in records
                          if r.timepoint == "before" and r.view_number > 0
                          and r.polarization == "non_polarized"}
        after_by_view = {r.view_number: r for r in records
                         if r.timepoint == "after" and r.view_number > 0
                         and r.polarization == "non_polarized"}
        n = 0
        for view in sorted(set(before_by_view) & set(after_by_view)):
            b_rec = before_by_view[view]
            a_rec = after_by_view[view]
            b_img = (cropped.get(b_rec.path)
                     if b_rec.path in cropped
                     else (wb_results[b_rec.path].image
                           if b_rec.path in wb_results
                           else white_balance._read_image(Path(b_rec.path))))
            a_img = (cropped.get(a_rec.path)
                     if a_rec.path in cropped
                     else (wb_results[a_rec.path].image
                           if a_rec.path in wb_results
                           else white_balance._read_image(Path(a_rec.path))))
            comp = composite.before_after(b_img, a_img, label=label_composites)
            out_path = ba_dir / f"v{view:02d}_before_after.jpg"
            composite.write_image(comp, out_path)
            n += 1
        print(f"  Wrote {n} before/after composites.")

    # 6. AACD board (one per timepoint that has any AACD-classifiable views)
    if "board" in steps:
        print("Building AACD boards...")
        board_dir = out_root / "boards"
        board_dir.mkdir(parents=True, exist_ok=True)
        for tp in ("before", "after"):
            tp_records = [r for r in records
                          if r.timepoint == tp and r.view_number > 0
                          and r.polarization == "non_polarized"]
            if not tp_records:
                continue
            views = {}
            for r in tp_records:
                img = (cropped.get(r.path)
                       if r.path in cropped
                       else (wb_results[r.path].image
                             if r.path in wb_results
                             else white_balance._read_image(Path(r.path))))
                # If we didn't crop this run, apply crop here to enforce aspect.
                if r.path not in cropped:
                    img = crop_aacd.aacd_crop(img, r.view_number)
                views[r.view_number] = img
            board = composite.aacd_board(views, standard=standard)
            out_path = board_dir / f"{tp}_board.png"
            composite.write_image(board, out_path)
            missing = [v for v in (range(1, 13) if standard == "aacd" else range(1, 14))
                       if v not in views]
            print(f"  {tp}: board → {out_path.name} (missing views: {missing or 'none'})")

    # 7. Report
    report_path = out_root / "report.md"
    with open(report_path, "w") as f:
        f.write(f"# Case Report — {case_folder.name}\n\n")
        f.write(f"Total images: {len(records)}\n\n")
        by_tp = defaultdict(int)
        by_view = defaultdict(int)
        for r in records:
            by_tp[r.timepoint] += 1
            by_view[r.view_number] += 1
        f.write("## By timepoint\n")
        for tp, n in sorted(by_tp.items()):
            f.write(f"- {tp}: {n}\n")
        f.write("\n## By view\n")
        for v, n in sorted(by_view.items()):
            label = classify.VIEW_LABELS.get(v, "unknown")
            f.write(f"- View {v} ({label}): {n}\n")
        unresolved = [r for r in records if r.view_number == 0 or r.timepoint == "unknown"]
        if unresolved:
            f.write("\n## Unresolved\n")
            for r in unresolved:
                f.write(f"- {r.path}: {r.notes}\n")
    print(f"\nReport → {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dental photo processor")
    parser.add_argument("case_folder", type=Path)
    parser.add_argument("--steps", default="wb,crop,polar,compose,board",
                        help="Comma-separated subset of: wb,crop,polar,compose,board")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="Pre-classified manifest CSV (skips classification)")
    parser.add_argument("--standard", choices=["aacd", "eaed"], default="aacd")
    parser.add_argument("--label", action="store_true",
                        help="Add 'Before / After' labels to composites")
    args = parser.parse_args()

    if not args.case_folder.exists():
        sys.exit(f"Case folder not found: {args.case_folder}")
    steps = set(s.strip() for s in args.steps.split(",") if s.strip())
    run(args.case_folder, steps=steps, manifest_path=args.manifest,
        standard=args.standard, label_composites=args.label)


if __name__ == "__main__":
    main()
