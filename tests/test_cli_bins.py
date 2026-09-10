"""CLI tests for the ``--bins`` flag.

These tests exercise ``__main__.main()`` end-to-end with the heavy
pipeline mocked out, so we can assert:

* validation failures exit with code 1 and the exact error message;
* a valid ``--bins`` value produces output with the right number of
  bin-break records;
* omitting ``--bins`` preserves the original (backwards-compatible)
  behavior.

We never touch the live Discogs API.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import pytest

from vinyl_sorter.models import VinylRecord


# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------

def _make_records(n: int) -> List[VinylRecord]:
    """Build ``n`` deterministic real records (no bin-break markers)."""
    return [
        VinylRecord(
            discogs_id=i + 1,
            release_title=f"Rec {i}",
            release_artist=f"Artist {i}",
            sort_artist=f"artist{i}",
            release_year=2000 + i,
            sort_year=2000 + i,
            sort_sequence=i + 1,
            instance_id=i + 1,
            cover_image_url=f"https://example.test/cover-{i}.jpg",
            thumb_url=f"https://example.test/thumb-{i}.jpg",
        )
        for i in range(n)
    ]


@pytest.fixture
def pipeline_mock(monkeypatch, tmp_path):
    """Mock the Discogs + cache + pipeline layers so ``main()`` runs offline.

    Returns:
        A function that takes a record count ``n`` and arranges the
        mocks to return a fresh ``n``-record fixture when the pipeline
        runs.
    """
    def _arrange(n: int, *, cache_hit: bool = False) -> List[VinylRecord]:
        fixture = _make_records(n)

        # No cache hits by default — keep the test surface minimal.
        monkeypatch.setattr(
            "vinyl_sorter.__main__.get_cache_metadata",
            lambda path: None,
        )
        monkeypatch.setattr(
            "vinyl_sorter.__main__.load_cache",
            lambda path: fixture if cache_hit else None,
        )
        monkeypatch.setattr(
            "vinyl_sorter.__main__.save_cache",
            lambda records, path: None,
        )
        monkeypatch.setattr(
            "vinyl_sorter.__main__._run_full_pipeline",
            lambda *a, **kw: list(fixture),
        )
        # No custom fields configured → skip persistence entirely.
        monkeypatch.setattr(
            "vinyl_sorter.__main__._resolve_fields",
            lambda api, config: ({}, False),
        )
        # Stub out the Discogs API client constructor (shouldn't be used
        # because we always short-circuit, but keep the import happy).
        monkeypatch.setattr("vinyl_sorter.__main__.DiscogsAPI", MagicMock())
        # No-op write-back (shouldn't be reached without has_fields).
        monkeypatch.setattr(
            "vinyl_sorter.__main__.write_back_sort_data",
            lambda *a, **kw: 0,
        )
        # Force --no-cache and --no-write-back so no I/O sneaks through.
        return fixture

    return _arrange


def _run_main(monkeypatch, tmp_path, *extra_args) -> int:
    """Invoke ``main()`` with ``--token X --no-cache --no-write-back`` plus extras.

    Returns the exit code. ``SystemExit`` is caught and converted into
    a regular integer return value.
    """
    argv = [
        "vinyl_sorter",
        "--token", "fake-token",
        "--no-cache",
        "--no-write-back",
        "--output", str(tmp_path / "out.csv"),
    ] + list(extra_args)
    monkeypatch.setattr(sys, "argv", argv)

    from vinyl_sorter.__main__ import main
    try:
        main()
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1


# ----------------------------------------------------------------------
# validation
# ----------------------------------------------------------------------

def test_bins_zero_exits_nonzero_with_error(monkeypatch, tmp_path, pipeline_mock, capsys):
    """``--bins 0`` → exit 1 with the 'at least 2' error message."""
    pipeline_mock(5)
    code = _run_main(monkeypatch, tmp_path, "--bins", "0")
    captured = capsys.readouterr()
    assert code == 1
    assert "Error: --bins must be at least 2 (got 0)." in captured.err


def test_bins_one_exits_nonzero_with_error(monkeypatch, tmp_path, pipeline_mock, capsys):
    """``--bins 1`` → exit 1 with the 'at least 2' error message."""
    pipeline_mock(5)
    code = _run_main(monkeypatch, tmp_path, "--bins", "1")
    captured = capsys.readouterr()
    assert code == 1
    assert "Error: --bins must be at least 2 (got 1)." in captured.err


def test_bins_exceeds_record_count_exits_nonzero(monkeypatch, tmp_path, pipeline_mock, capsys):
    """``--bins N`` with N > record count → exit 1 with the right error."""
    pipeline_mock(5)
    code = _run_main(monkeypatch, tmp_path, "--bins", "100")
    captured = capsys.readouterr()
    assert code == 1
    assert "Error: --bins (100) cannot exceed number of records (5)." in captured.err


def test_bins_negative_exits_nonzero(monkeypatch, tmp_path, pipeline_mock, capsys):
    """``--bins -3`` → exit 1 (covered by the 'must be at least 2' check)."""
    pipeline_mock(5)
    code = _run_main(monkeypatch, tmp_path, "--bins", "-3")
    captured = capsys.readouterr()
    assert code == 1
    assert "Error: --bins must be at least 2 (got -3)." in captured.err


# ----------------------------------------------------------------------
# happy path
# ----------------------------------------------------------------------

def test_bins_omitted_no_bin_breaks(monkeypatch, tmp_path, pipeline_mock):
    """Without ``--bins``, the CSV has no 'Bin Break' rows."""
    pipeline_mock(5)
    code = _run_main(monkeypatch, tmp_path)
    assert code == 0
    out_path = tmp_path / "out.csv"
    assert out_path.exists()
    with out_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 5
    assert all(r["Album"] != "Bin Break" for r in rows)


def test_bins_two_produces_one_break_in_csv(monkeypatch, tmp_path, pipeline_mock, capsys):
    """``--bins 2`` on 5 records → 1 bin break (2 records, break, 3 records)."""
    pipeline_mock(5)
    code = _run_main(monkeypatch, tmp_path, "--bins", "2")
    assert code == 0
    captured = capsys.readouterr()
    assert "Inserted 1 bin break(s) into the sorted list." in captured.out

    out_path = tmp_path / "out.csv"
    with out_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 6
    break_rows = [r for r in rows if r["Album"] == "Bin Break"]
    assert len(break_rows) == 1


def test_bins_three_produces_two_breaks(monkeypatch, tmp_path, pipeline_mock):
    """``--bins 3`` on 6 records → 2 bin breaks."""
    pipeline_mock(6)
    code = _run_main(monkeypatch, tmp_path, "--bins", "3")
    assert code == 0
    out_path = tmp_path / "out.csv"
    with out_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 8
    break_rows = [r for r in rows if r["Album"] == "Bin Break"]
    assert len(break_rows) == 2


def test_bins_works_with_json_format(monkeypatch, tmp_path, pipeline_mock):
    """``--bins 2 --format json`` → JSON file contains bin break entries."""
    pipeline_mock(5)
    argv = [
        "vinyl_sorter",
        "--token", "fake-token",
        "--no-cache",
        "--no-write-back",
        "--output", str(tmp_path / "out.json"),
        "--format", "json",
        "--bins", "2",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    from vinyl_sorter.__main__ import main
    main()

    out_path = tmp_path / "out.json"
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data) == 6
    breaks = [r for r in data if r.get("is_bin_break")]
    assert len(breaks) == 1
    assert breaks[0]["release_title"] == "Bin Break"


def test_bins_full_collection_size_equals_record_count(monkeypatch, tmp_path, pipeline_mock):
    """``--bins N`` with N == record count → no breaks (every bin has 1 record)."""
    pipeline_mock(5)
    code = _run_main(monkeypatch, tmp_path, "--bins", "5")
    assert code == 0
    out_path = tmp_path / "out.csv"
    with out_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # 5 records, 4 bin breaks (between 5 adjacent bins).
    assert len(rows) == 9
    assert sum(1 for r in rows if r["Album"] == "Bin Break") == 4
