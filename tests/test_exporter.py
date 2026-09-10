"""Exporter tests — CSV + JSON, including bin-break handling.

These tests don't touch the network or filesystem: each test uses a
``tmp_path`` fixture and the in-memory record builders from the
binning tests.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import List

from vinyl_sorter.binning import insert_bin_breaks
from vinyl_sorter.exporter import export_collection, export_collection_json, record_to_dict
from vinyl_sorter.models import VinylRecord


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

CSV_HEADERS = [
    "Sort #", "Sort Artist", "Artist", "Album",
    "Sort Year", "Sort Month", "Year", "Live", "Compilation",
]


def _make_records(n: int) -> List[VinylRecord]:
    """Build ``n`` synthetic real records."""
    return [
        VinylRecord(
            discogs_id=i + 1,
            release_title=f"Rec {i}",
            release_artist=f"Artist {i}",
            sort_artist=f"artist{i}",
            release_year=2000 + i,
            sort_year=2000 + i,
            sort_month=0,
            sort_sequence=i + 1,
            instance_id=i + 1,
            cover_image_url=f"https://example.test/cover-{i}.jpg",
            thumb_url=f"https://example.test/thumb-{i}.jpg",
        )
        for i in range(n)
    ]


def _read_csv(path: Path) -> List[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ----------------------------------------------------------------------
# CSV
# ----------------------------------------------------------------------

def test_export_csv_normal_records_only(tmp_path: Path) -> None:
    """Sanity check: a pure real-record list still renders cleanly."""
    out = tmp_path / "out.csv"
    export_collection(_make_records(3), output_file=str(out))
    rows = _read_csv(out)
    assert len(rows) == 3
    assert rows[0]["Sort #"] == "1"
    assert rows[0]["Album"] == "Rec 0"
    assert rows[0]["Artist"] == "Artist 0"


def test_export_csv_bin_break_row_album_label_only(tmp_path: Path) -> None:
    """A bin-break row writes Album='Bin Break' and all other columns blank."""
    records = _make_records(3)
    binned = insert_bin_breaks(records, b=2)
    out = tmp_path / "out.csv"
    export_collection(binned, output_file=str(out))
    rows = _read_csv(out)
    assert len(rows) == 4
    # With compute_bin_sizes(3, 2) == [2, 1], the break sits at index 2
    # (after the two-record first bin).
    break_row = rows[2]
    assert break_row["Album"] == "Bin Break"
    # Every other column (including Sort #, Sort Artist, Artist, Year, etc.) is blank.
    for header in CSV_HEADERS:
        if header == "Album":
            continue
        assert break_row[header] == "", f"bin-break row column '{header}' must be blank, got {break_row[header]!r}"


def test_export_csv_bin_break_preserves_normal_rows(tmp_path: Path) -> None:
    """Normal rows around a bin break are unchanged."""
    records = _make_records(5)
    binned = insert_bin_breaks(records, b=3)
    out = tmp_path / "out.csv"
    export_collection(binned, output_file=str(out))
    rows = _read_csv(out)
    # All non-break rows still have their full data.
    real_rows = [r for r in rows if r["Album"] != "Bin Break"]
    assert len(real_rows) == 5
    assert real_rows[0]["Sort #"] == "1"
    assert real_rows[4]["Sort #"] == "5"


def test_export_csv_no_break_rows_when_binning_omitted(tmp_path: Path) -> None:
    """No binning → no 'Bin Break' CSV rows."""
    records = _make_records(5)
    out = tmp_path / "out.csv"
    export_collection(records, output_file=str(out))
    rows = _read_csv(out)
    assert all(r["Album"] != "Bin Break" for r in rows)


# ----------------------------------------------------------------------
# JSON
# ----------------------------------------------------------------------

def test_record_to_dict_normal_includes_is_bin_break_false() -> None:
    """Normal records serialize with ``is_bin_break: False``."""
    record = _make_records(1)[0]
    d = record_to_dict(record)
    assert d["is_bin_break"] is False
    # Schema fields preserved.
    assert d["discogs_id"] == 1
    assert d["release_title"] == "Rec 0"
    assert d["cover_image_url"] == "https://example.test/cover-0.jpg"


def test_record_to_dict_bin_break_marker_present() -> None:
    """Bin break records serialize with ``is_bin_break: True``."""
    records = _make_records(4)
    binned = insert_bin_breaks(records, b=2)
    break_record = next(r for r in binned if r.is_bin_break)
    d = record_to_dict(break_record)
    assert d["is_bin_break"] is True
    assert d["release_title"] == "Bin Break"
    # Blank/null-shaped payload per spec.
    assert d["release_artist"] == ""
    assert d["release_year"] == -1
    assert d["cover_image_url"] == ""
    assert d["thumb_url"] == ""


def test_export_collection_json_mixed_records() -> None:
    """Mixed list (real + bin break) serializes cleanly."""
    records = _make_records(4)
    binned = insert_bin_breaks(records, b=2)
    out = export_collection_json(binned)
    assert len(out) == 5
    # Find the break in the output.
    breaks = [r for r in out if r.get("is_bin_break")]
    assert len(breaks) == 1
    assert breaks[0]["is_bin_break"] is True
    assert breaks[0]["release_title"] == "Bin Break"


def test_export_collection_json_schema_unchanged_for_normal_records() -> None:
    """Adding ``is_bin_break`` to the schema must not break existing keys."""
    record = _make_records(1)[0]
    d = record_to_dict(record)
    expected_keys = {
        "discogs_id", "sort_sequence", "release_artist", "release_artist_id",
        "sort_artist", "release_title", "release_year", "sort_year",
        "sort_month", "is_compilation", "is_live",
        "cover_image_url", "date_added", "thumb_url",
        "instance_id", "folder_id", "import_number",
        "is_bin_break",
    }
    assert set(d.keys()) == expected_keys


def test_export_collection_json_file_round_trip(tmp_path: Path) -> None:
    """JSON export file contains both kinds of records in the right order."""
    records = _make_records(3)
    binned = insert_bin_breaks(records, b=3)
    out_path = tmp_path / "out.json"
    from vinyl_sorter.exporter import export_collection_json_file
    export_collection_json_file(binned, output_file=str(out_path))
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data) == 5
    # Position 0 is real, position 1 is break, position 2 is real, position 3 is break, position 4 is real.
    assert data[0]["release_title"] == "Rec 0"
    assert data[1]["is_bin_break"] is True
    assert data[2]["release_title"] == "Rec 1"
    assert data[3]["is_bin_break"] is True
    assert data[4]["release_title"] == "Rec 2"
