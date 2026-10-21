"""Tests for the Genre sort mode data path.

Covers the four pieces the front end depends on: the ``VinylRecord`` fields,
the canonical exporter schema, the cache round-trip (and its version bump),
and the pydantic API schema.  Also covers ``enrich_genres()`` — the parser
phase that keeps Discogs fetch cost off cache-warm runs.

No network access: ``DiscogsAPI`` is replaced with a local fake.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from vinyl_sorter.api import RecordResponse
from vinyl_sorter.binning import insert_bin_breaks
from vinyl_sorter.cache import (
    CACHE_SCHEMA_VERSION,
    _cache_dict_to_record,
    _record_to_cache_dict,
)
from vinyl_sorter.exporter import record_to_dict
from vinyl_sorter.models import VinylRecord
from vinyl_sorter.parser import enrich_genres


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _record(genres: List[str], styles: List[str], discogs_id: int = 1) -> VinylRecord:
    """Build a record carrying the given Discogs genre/style payload."""
    return VinylRecord(
        discogs_id=discogs_id,
        release_artist="Test Artist",
        release_title="Test Album",
        release_year=1999,
        sort_sequence=1,
        genres=list(genres),
        styles=list(styles),
    )


def _with_bin_break(records: List[VinylRecord]) -> List[VinylRecord]:
    """Return ``records`` with one synthetic bin-break row interleaved.

    ``insert_bin_breaks`` inserts ``b - 1`` separators, so b=2 over two
    records is the smallest call that actually yields a bin break.
    """
    two_records = list(records)
    while len(two_records) < 2:
        two_records.append(
            VinylRecord(
                discogs_id=len(two_records) + 1,
                release_title=f"Filler {len(two_records)}",
                sort_sequence=len(two_records) + 1,
            )
        )
    binned = insert_bin_breaks(two_records, b=2)
    assert any(r.is_bin_break for r in binned), "helper must produce a bin break"
    return binned


class _FakeDiscogsAPI:
    """Stand-in for DiscogsAPI that records which releases were fetched.

    Mirrors ``lookup_release_genres()``'s contract: returns
    ``(genres, styles)`` and never raises.
    """

    def __init__(self, table: Dict[int, Tuple[List[str], List[str]]]) -> None:
        self._table = table
        self.calls: List[int] = []

    def lookup_release_genres(self, release_id: int) -> Tuple[List[str], List[str]]:
        self.calls.append(release_id)
        return self._table.get(release_id, ([], []))


# ----------------------------------------------------------------------
# 1–2. Exporter schema
# ----------------------------------------------------------------------

def test_record_to_dict_includes_genres_and_styles() -> None:
    """A normal record serializes its Discogs genres and styles."""
    d = record_to_dict(_record(["Rock", "Pop"], ["Dream Pop"]))
    assert d["genres"] == ["Rock", "Pop"]
    assert d["styles"] == ["Dream Pop"]


def test_record_to_dict_genres_default_empty() -> None:
    """A record with no Discogs genre data serializes empty lists, not null."""
    d = record_to_dict(VinylRecord(discogs_id=2, release_title="Bare"))
    assert d["genres"] == []
    assert d["styles"] == []


def test_record_to_dict_bin_break_has_stable_key_set() -> None:
    """Bin-break rows keep the schema and emit empty genre/style lists.

    Consumers rely on a constant key set across both record kinds, so this
    asserts the full key set rather than just the two new keys.
    """
    binned = _with_bin_break([_record(["Rock"], [], discogs_id=1)])
    break_record = next(r for r in binned if r.is_bin_break)
    d = record_to_dict(break_record)
    assert d["genres"] == []
    assert d["styles"] == []
    # Same key set as a normal record.
    assert set(d.keys()) == set(record_to_dict(_record([], [])).keys())


# ----------------------------------------------------------------------
# 3–5. Cache round-trip and version
# ----------------------------------------------------------------------

def test_cache_round_trip_preserves_genres_and_styles() -> None:
    """genres/styles survive cache save → load unchanged."""
    original = _record(["Rock", "Pop"], ["Dream Pop", "Shoegaze"], discogs_id=42)
    original.date_added = None
    restored = _cache_dict_to_record(_record_to_cache_dict(original))

    assert restored.discogs_id == 42
    assert restored.genres == ["Rock", "Pop"]
    assert restored.styles == ["Dream Pop", "Shoegaze"]


def test_cache_restore_defaults_missing_genres_to_empty() -> None:
    """Legacy/hand-edited cache entries without the keys restore as []."""
    for d in ({}, {"genres": None}, {"genres": None, "styles": None}):
        restored = _cache_dict_to_record(d)
        assert restored.genres == [], f"genres should default to [] for {d!r}"
        assert restored.styles == [], f"styles should default to [] for {d!r}"


def test_cache_schema_version_bumped_to_3() -> None:
    """Version 3 is what forces stale v2 caches to be discarded."""
    assert CACHE_SCHEMA_VERSION == 3


# ----------------------------------------------------------------------
# 6. API schema
# ----------------------------------------------------------------------

def test_record_response_accepts_genres_and_styles() -> None:
    """RecordResponse carries both lists through to the API payload."""
    payload = record_to_dict(_record(["Jazz", "Rock"], ["Modal"]))
    response = RecordResponse(**payload)
    assert response.genres == ["Jazz", "Rock"]
    assert response.styles == ["Modal"]
    dumped = response.model_dump()
    assert dumped["genres"] == ["Jazz", "Rock"]
    assert dumped["styles"] == ["Modal"]


def test_record_response_defaults_genres_to_empty() -> None:
    """Records arriving without the keys still validate."""
    response = RecordResponse(**record_to_dict(VinylRecord(discogs_id=3)))
    assert response.genres == []
    assert response.styles == []


# ----------------------------------------------------------------------
# 7. Genre enrichment phase
# ----------------------------------------------------------------------

def test_enrich_genres_only_fetches_records_without_data() -> None:
    """Records already carrying data are never re-fetched.

    This is what makes a cache-warm run cost zero Discogs calls.
    """
    warm = _record(["Rock"], [], discogs_id=1)
    style_only = _record([], ["Shoegaze"], discogs_id=2)
    cold = _record([], [], discogs_id=3)

    api = _FakeDiscogsAPI({3: (["Electronic"], ["IDM"])})
    counters = enrich_genres([warm, style_only, cold], api)

    assert api.calls == [3], f"only the data-less record should be fetched, got {api.calls}"
    assert counters == {"total": 3, "from_payload": 2, "fetched": 1, "failed": 0}
    assert cold.genres == ["Electronic"]
    assert cold.styles == ["IDM"]
    # The warm records are untouched.
    assert warm.genres == ["Rock"]
    assert style_only.styles == ["Shoegaze"]


def test_enrich_genres_makes_no_calls_when_all_records_are_warm() -> None:
    """A fully cache-warm run issues zero Discogs requests."""
    api = _FakeDiscogsAPI({})
    records = [_record(["Rock"], [], discogs_id=i) for i in range(1, 6)]

    counters = enrich_genres(records, api)

    assert api.calls == []
    assert counters["fetched"] == 0


def test_enrich_genres_counts_failures_without_aborting() -> None:
    """A lookup that yields nothing leaves [] and does not stop the run."""
    api = _FakeDiscogsAPI({2: (["Rock"], [])})  # release 1 is missing from the table
    records = [_record([], [], discogs_id=1), _record([], [], discogs_id=2)]

    counters = enrich_genres(records, api)

    assert counters["failed"] == 1
    assert counters["fetched"] == 1
    assert records[0].genres == []
    assert records[1].genres == ["Rock"]


def test_enrich_genres_looks_up_records_with_no_genres_at_all() -> None:
    """A real record with no genre data still gets its own lookup."""
    binned = insert_bin_breaks(
        [_record([], [], discogs_id=1), _record(["Jazz"], [], discogs_id=2)],
        b=2,
    )
    api = _FakeDiscogsAPI({1: (["Rock"], [])})

    enrich_genres(binned, api)

    assert api.calls == [1], "only the genre-less real record should be fetched"
    """Bin-break separators are synthetic and are not looked up."""
    binned = insert_bin_breaks(
        [_record(["Rock"], [], discogs_id=1), _record(["Jazz"], [], discogs_id=2)],
        b=2,
    )
    assert any(r.is_bin_break for r in binned)
    api = _FakeDiscogsAPI({})

    counters = enrich_genres(binned, api)

    # Only the bin-break row could have triggered a lookup; both real
    # records already carry genre data.
    assert api.calls == []
    assert counters["total"] == 2