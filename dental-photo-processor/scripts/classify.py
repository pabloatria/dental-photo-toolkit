"""Classify dental case photos by timepoint, polarization, and AACD view.

Reads filenames and (when available) EXIF to produce a manifest. The classifier
is intentionally forgiving: ambiguous files get `view = unknown` and are
written to manifest.csv so the user can resolve them once and re-run.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".cr3", ".cr2",
              ".nef", ".arw", ".dng", ".raf", ".rw2", ".orf"}

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
    13: ["1to1", "oneone", "close_anterior", "anterior_closeup"],
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
    13: "EAED 1:1 anterior close-up",
}


@dataclass
class PhotoRecord:
    path: str
    timepoint: str        # before | after | interim | unknown
    polarization: str     # polarized | non_polarized | unknown
    view_number: int      # 0 = unknown, 1..13 per VIEW_LABELS
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
    if _matches_any(name_lower, POLARIZATION_PATTERNS["non_polarized_explicit"]):
        return "non_polarized"
    return "non_polarized"  # default — most clinical shots are non-pol


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
            path=str(path),
            timepoint=timepoint,
            polarization=polarization,
            view_number=view_num,
            view_label=VIEW_LABELS.get(view_num, "unknown"),
            notes="; ".join(notes),
        ))
    return records


def write_manifest(records: Iterable[PhotoRecord], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(next(iter(records))).keys())
                                if records else
                                ["path", "timepoint", "polarization", "view_number", "view_label", "notes"])
        writer.writeheader()
        for r in records:
            writer.writerow(asdict(r))


def read_manifest(path: Path) -> list[PhotoRecord]:
    records = []
    with open(path) as f:
        for row in csv.DictReader(f):
            records.append(PhotoRecord(
                path=row["path"],
                timepoint=row["timepoint"],
                polarization=row["polarization"],
                view_number=int(row["view_number"]),
                view_label=row["view_label"],
                notes=row.get("notes", ""),
            ))
    return records


def has_unresolved(records: Iterable[PhotoRecord]) -> bool:
    return any(r.timepoint == "unknown" or r.view_number == 0 for r in records)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("case_folder", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    records = scan_case(args.case_folder)
    out = args.out or args.case_folder / "_processed" / "manifest.csv"
    write_manifest(records, out)
    print(f"Wrote {len(records)} records to {out}")
    if has_unresolved(records):
        print("Some records have unresolved timepoint or view. Edit the CSV and re-run.")
