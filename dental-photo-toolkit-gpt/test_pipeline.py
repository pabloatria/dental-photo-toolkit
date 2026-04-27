"""Smoke test: run pipeline on a synthetic JPEG case, assert outputs exist."""
import shutil
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
