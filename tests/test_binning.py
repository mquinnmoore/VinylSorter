"""Unit + integration tests for ``vinyl_sorter.binning``.

The binning module is pure (no I/O, no network, no global state),
so every test is a fast in-memory assertion.
"""

from __future__ import annotations

from typing import List

import pytest

from vinyl_sorter.binning import compute_bin_sizes, insert_bin_breaks
from vinyl_sorter.models import VinylRecord


# ----------------------------------------------------------------------
# compute_bin_sizes
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "n, b, expected",
    [
        # The four cases called out explicitly in the spec.
        (91, 3, [30, 31, 30]),
        (90, 4, [22, 23, 23, 22]),
        (100, 3, [33, 34, 33]),
        (60, 3, [20, 20, 20]),  # even split
        # Additional sanity checks.
        (95, 3, [31, 32, 32]),   # rem=2 → middle + (middle+1)
        (97, 3, [32, 33, 32]),   # rem=1 → middle only
        (60, 2, [30, 30]),        # even split across two bins
        (10, 2, [5, 5]),          # tiny even split
        (100, 10, [10] * 10),     # even split across many bins
    ],
)
def test_compute_bin_sizes(n: int, b: int, expected: List[int]) -> None:
    """Each row in the parametrize table is a documented spec example."""
    assert compute_bin_sizes(n, b) == expected


def test_compute_bin_sizes_sum_matches_n() -> None:
    """Bin sizes must sum to ``n`` for a wide range of (n, b) pairs."""
    for n, b in [
        (1, 1), (2, 1), (2, 2), (3, 2), (5, 3), (10, 4),
        (60, 3), (91, 3), (97, 3), (100, 3), (100, 10),
    ]:
        sizes = compute_bin_sizes(n, b)
        assert sum(sizes) == n, f"n={n}, b={b}: sizes={sizes}"
        assert len(sizes) == b, f"n={n}, b={b}: got {len(sizes)} sizes"
        assert all(s >= 0 for s in sizes), f"n={n}, b={b}: negative size"


def test_compute_bin_sizes_max_minus_min_is_le_one() -> None:
    """Middle-balanced distribution: sizes differ by at most one."""
    for n, b in [
        (91, 3), (100, 3), (97, 3), (95, 3), (90, 4), (60, 3), (100, 10), (10, 2),
    ]:
        sizes = compute_bin_sizes(n, b)
        assert max(sizes) - min(sizes) <= 1, f"n={n}, b={b}: sizes={sizes}"


def test_compute_bin_sizes_middle_first() -> None:
    """When ``n % b == 1``, the +1 lands on the middle bin."""
    sizes = compute_bin_sizes(7, 3)  # base=2, rem=1 → middle bin gets +1
    assert sizes == [2, 3, 2]


# ----------------------------------------------------------------------
# insert_bin_breaks
# ----------------------------------------------------------------------

def _make_records(n: int) -> List[VinylRecord]:
    """Build ``n`` synthetic records with a deterministic title.

    Records get sequential titles ("Rec 0", "Rec 1", ...) so tests
    can match positions after binning.
    """
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


def test_insert_bin_breaks_output_length_matches_records_plus_breaks() -> None:
    """``len(result) == len(records) + (b - 1)``."""
    for n, b in [(3, 2), (5, 2), (10, 3), (91, 3), (100, 5)]:
        records = _make_records(n)
        result = insert_bin_breaks(records, b)
        assert len(result) == n + (b - 1), f"n={n}, b={b}: got {len(result)}"


def test_insert_bin_breaks_three_records_two_bins_layout() -> None:
    """3 records + 2 bins → output length 4 (one bin break between two bins).

    With ``compute_bin_sizes(3, 2) == [2, 1]`` (the same middle-balanced
    algorithm that produces ``compute_bin_sizes(90, 4) == [22, 23, 23, 22]``),
    the first bin gets 2 records and the second gets 1.
    """
    records = _make_records(3)
    result = insert_bin_breaks(records, b=2)
    assert len(result) == 4
    # r0 r1 | break | r2
    assert result[0].release_title == "Rec 0"
    assert result[1].release_title == "Rec 1"
    assert result[2].is_bin_break is True
    assert result[3].release_title == "Rec 2"


def test_insert_bin_breaks_breaks_carry_marker_and_title() -> None:
    """Every break record has ``is_bin_break=True`` and ``release_title='Bin Break'``."""
    records = _make_records(20)
    result = insert_bin_breaks(records, b=4)
    breaks = [r for r in result if r.is_bin_break]
    assert len(breaks) == 3  # b - 1
    assert all(r.release_title == "Bin Break" for r in breaks)


def test_insert_bin_breaks_91_records_3_bins_splits_correctly() -> None:
    """Spec example: 91 records + 3 bins → sizes [30, 31, 30]."""
    records = _make_records(91)
    result = insert_bin_breaks(records, b=3)
    # Walk the result and slice on bin break boundaries.
    bins: List[List[VinylRecord]] = [[]]
    for r in result:
        if r.is_bin_break:
            bins.append([])
        else:
            bins[-1].append(r)
    sizes = [len(b) for b in bins]
    assert sizes == [30, 31, 30]
    # And the total length check.
    assert len(result) == 91 + 2
    # The original records are still in their original order, untouched.
    real = [r for r in result if not r.is_bin_break]
    assert real == records


def test_insert_bin_breaks_records_argument_not_mutated() -> None:
    """``insert_bin_breaks`` must return a new list — input is untouched."""
    records = _make_records(5)
    snapshot = list(records)
    insert_bin_breaks(records, b=2)
    assert records == snapshot


def test_insert_bin_breaks_bin_break_records_have_sentinel_shape() -> None:
    """Bin break records carry sentinel fields so the exporter can blank them."""
    records = _make_records(4)
    result = insert_bin_breaks(records, b=2)
    break_record = next(r for r in result if r.is_bin_break)
    assert break_record.discogs_id == -1
    assert break_record.instance_id == -1
    assert break_record.sort_sequence == -1
    assert break_record.release_artist == ""
    assert break_record.cover_image_url == ""
    assert break_record.thumb_url == ""


def test_insert_bin_breaks_no_extra_real_records_lost_or_added() -> None:
    """Inserting breaks must not lose or duplicate any real record."""
    records = _make_records(42)
    result = insert_bin_breaks(records, b=7)
    real_records = [r for r in result if not r.is_bin_break]
    assert real_records == records


def test_insert_bin_breaks_does_not_assign_sort_sequence_to_breaks() -> None:
    """Bin break records must NOT carry a real ``sort_sequence``.

    They use the sentinel ``-1`` so the CSV row's Sort # column
    stays blank and the cover flow position line stays sane.
    """
    records = _make_records(15)
    result = insert_bin_breaks(records, b=3)
    for r in result:
        if r.is_bin_break:
            assert r.sort_sequence == -1
