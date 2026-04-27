"""Smoke test: run pipeline on a synthetic JPEG case, assert outputs exist."""
import csv
import io
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
SYNTH_SCRIPT = ROOT / "dental-photo-processor" / "scripts" / "_make_test_case.py"


def test_pipeline_end_to_end(tmp_path):
    case = tmp_path / "case"
    subprocess.run([sys.executable, str(SYNTH_SCRIPT), str(case)], check=True)
    out_zip = tmp_path / "out.zip"
    subprocess.run(
        [sys.executable, str(HERE / "pipeline.py"), str(case), "--output", str(out_zip)],
        check=True,
    )
    assert out_zip.exists()
    with zipfile.ZipFile(out_zip) as z:
        names = z.namelist()
    assert any("aacd_board" in n for n in names), f"no AACD board in zip: {names}"
    assert any("before_after" in n for n in names), f"no before/after in zip: {names}"
    assert any("manifest.csv" in n for n in names)
    assert any("report.md" in n for n in names)

    # Board PNG should be a non-trivial image (>100 KB at 300 dpi 11x8.5)
    with zipfile.ZipFile(out_zip) as z:
        board_names = [n for n in names if n.endswith("aacd_board.png")]
        assert board_names, "no board png in zip"
        with z.open(board_names[0]) as f:
            assert len(f.read()) > 100_000, "board PNG suspiciously small"

        # Manifest should have 24 rows (12 views x 2 timepoints) for the synthetic case
        with z.open("manifest.csv") as raw:
            rows = list(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8")))
        assert len(rows) == 24, f"expected 24 manifest rows, got {len(rows)}"
        assert all(r["view_number"] != "0" for r in rows), \
            "synthetic case should classify every view"

        # WB and crops directories should each contain JPEGs
        assert any(n.startswith("wb/") and n.endswith(".jpg") for n in names)
        assert any(n.startswith("crops/") and n.endswith(".jpg") for n in names)
