"""Smoke test + security regression tests for the GPT pipeline."""
import csv
import io
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

HERE = Path(__file__).parent
ROOT = HERE.parent
SYNTH_SCRIPT = ROOT / "dental-photo-processor" / "scripts" / "_make_test_case.py"

sys.path.insert(0, str(HERE))
import pipeline  # noqa: E402


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


# ---------------------------------------------------------------- security


def test_safe_unzip_rejects_traversal(tmp_path):
    """A ZIP entry with ../ in its path must raise, not write outside dest."""
    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w") as z:
        z.writestr("../escape.txt", b"pwned")
    dest = tmp_path / "dest"
    with pytest.raises(RuntimeError, match="Unsafe path"):
        pipeline.safe_unzip(bad_zip, dest)
    assert not (tmp_path / "escape.txt").exists(), "traversal succeeded"


def test_safe_unzip_rejects_absolute(tmp_path):
    """A ZIP entry with an absolute path must raise."""
    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w") as z:
        z.writestr("/etc/passwd_fake", b"pwned")
    dest = tmp_path / "dest"
    with pytest.raises(RuntimeError, match="Unsafe path"):
        pipeline.safe_unzip(bad_zip, dest)


def test_safe_unzip_extracts_clean_archive(tmp_path):
    """A well-formed ZIP must extract normally."""
    good_zip = tmp_path / "good.zip"
    with zipfile.ZipFile(good_zip, "w") as z:
        z.writestr("a.txt", b"hello")
        z.writestr("sub/b.txt", b"world")
    dest = tmp_path / "dest"
    pipeline.safe_unzip(good_zip, dest)
    assert (dest / "a.txt").read_bytes() == b"hello"
    assert (dest / "sub" / "b.txt").read_bytes() == b"world"


def test_image_bomb_dimensions_rejected(tmp_path):
    """A header claiming dimensions over MAX_PIXELS must raise before decode.

    We use 12000 × 12000 = 144M pixels — bigger than our 80M cap but smaller
    than Pillow's 2×-MAX bomb threshold (160M), so our explicit check fires
    rather than Pillow's. Either path rejects, both are tested by the message.
    """
    import struct
    import zlib

    sig = b"\x89PNG\r\n\x1a\n"
    w = h = 12_000  # 144M pixels — tests our cap, under Pillow's bomb threshold
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit RGB
    ihdr = b"IHDR" + ihdr_data
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + ihdr + struct.pack(">I", zlib.crc32(ihdr))
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    bomb = tmp_path / "bomb.png"
    bomb.write_bytes(sig + ihdr_chunk + iend)
    # Either our explicit cap or Pillow's bomb guard rejects — both are valid wins
    with pytest.raises(RuntimeError, match="(too large|decompression bomb|exceeds limit)"):
        pipeline._read_image(bomb)


def test_pillow_extreme_bomb_rejected(tmp_path):
    """Sanity: Pillow's own bomb guard catches truly egregious dimensions."""
    import struct
    import zlib

    sig = b"\x89PNG\r\n\x1a\n"
    w = h = 100_000  # 10B pixels — Pillow's guard fires before ours
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr = b"IHDR" + ihdr_data
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + ihdr + struct.pack(">I", zlib.crc32(ihdr))
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    bomb = tmp_path / "bomb.png"
    bomb.write_bytes(sig + ihdr_chunk + iend)
    with pytest.raises(RuntimeError):
        pipeline._read_image(bomb)
