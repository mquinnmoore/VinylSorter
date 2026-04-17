"""Local JSON cache for the sorted vinyl collection.

Saves the fully sorted collection to a local JSON file so that subsequent
startups can load instantly without hitting the Discogs API.  A lightweight
count check against Discogs detects when the cache is likely stale (new
records added or removed).

Note: The count check is a heuristic — it catches adds and removes but
*not* edits to existing records.  Use ``--refresh`` for a guaranteed
fresh load.
"""

from __future__ import annotations

import json
import logging
from dataclasses import fields as dataclass_fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import ArtistType
from .models import VinylRecord

logger = logging.getLogger(__name__)

DEFAULT_CACHE_FILE = ".vinyl_sorter_cache.json"


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _record_to_cache_dict(record: VinylRecord) -> Dict[str, Any]:
    """Convert a VinylRecord to a dict suitable for JSON cache storage.

    This includes ALL fields needed to fully reconstruct the object,
    unlike ``exporter.record_to_dict()`` which is optimized for display.
    """
    return {
        "discogs_id": record.discogs_id,
        "release_artist": record.release_artist,
        "release_artist_id": record.release_artist_id,
        "release_title": record.release_title,
        "release_year": record.release_year,
        "instance_id": record.instance_id,
        "folder_id": record.folder_id,
        "persisted_sort_artist": record.persisted_sort_artist,
        "persisted_sort_year": record.persisted_sort_year,
        "persisted_sort_month": record.persisted_sort_month,
        "persisted_is_compilation": record.persisted_is_compilation,
        "release_artist_type": record.release_artist_type.value,
        "is_compilation": record.is_compilation,
        "is_live": record.is_live,
        "sort_artist": record.sort_artist,
        "sort_year": record.sort_year,
        "sort_month": record.sort_month,
        "sort_sequence": record.sort_sequence,
        "cover_image_url": record.cover_image_url,
        "thumb_url": record.thumb_url,
        "import_number": record.import_number,
    }


def _cache_dict_to_record(d: Dict[str, Any]) -> VinylRecord:
    """Reconstruct a VinylRecord from a cache dict.

    All sort fields are restored exactly so the record sorts identically
    to a fresh-loaded one.
    """
    record = VinylRecord.__new__(VinylRecord)
    # Bypass __post_init__ — we set all fields explicitly
    record.discogs_id = d.get("discogs_id", -1)
    record.release_artist = d.get("release_artist", "None")
    record.release_artist_id = d.get("release_artist_id", -1)
    record.release_title = d.get("release_title", "None")
    record.release_year = d.get("release_year", -1)
    record.instance_id = d.get("instance_id", -1)
    record.folder_id = d.get("folder_id", 0)
    record.persisted_sort_artist = d.get("persisted_sort_artist")
    record.persisted_sort_year = d.get("persisted_sort_year")
    record.persisted_sort_month = d.get("persisted_sort_month")
    record.persisted_is_compilation = d.get("persisted_is_compilation")

    # Enum reconstruction
    artist_type_val = d.get("release_artist_type", "unknown")
    try:
        record.release_artist_type = ArtistType(artist_type_val)
    except ValueError:
        record.release_artist_type = ArtistType.UNKNOWN

    record.is_compilation = d.get("is_compilation", False)
    record.is_live = d.get("is_live", False)
    record.sort_artist = d.get("sort_artist", "None")
    record.sort_year = d.get("sort_year", -1)
    record.sort_month = d.get("sort_month", 0)
    record.sort_sequence = d.get("sort_sequence", -1)
    record.cover_image_url = d.get("cover_image_url", "")
    record.thumb_url = d.get("thumb_url", "")
    record.import_number = d.get("import_number", -1)

    return record


# ---------------------------------------------------------------------------
# Human-friendly time formatting
# ---------------------------------------------------------------------------

def _human_time_ago(dt: datetime) -> str:
    """Format a datetime as a human-friendly 'X ago' string.

    Examples: '2 hours ago', '3 days ago', 'just now'.
    """
    now = datetime.now(timezone.utc)
    delta = now - dt

    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    months = days // 30
    return f"{months} month{'s' if months != 1 else ''} ago"


# ---------------------------------------------------------------------------
# Cache metadata (lightweight — doesn't load all records)
# ---------------------------------------------------------------------------

class CacheMetadata:
    """Lightweight metadata about the cache file."""

    def __init__(
        self,
        cached_at: datetime,
        record_count: int,
        cache_file: str,
    ) -> None:
        self.cached_at = cached_at
        self.record_count = record_count
        self.cache_file = cache_file

    @property
    def cached_ago(self) -> str:
        """Human-friendly time since cache was written."""
        return _human_time_ago(self.cached_at)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for API responses."""
        return {
            "cached_at": self.cached_at.isoformat(),
            "record_count": self.record_count,
            "cached_ago": self.cached_ago,
            "cache_file": self.cache_file,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_cache_metadata(cache_file: str = DEFAULT_CACHE_FILE) -> Optional[CacheMetadata]:
    """Check if a cache file exists and return its metadata without loading records.

    Args:
        cache_file: Path to the cache file.

    Returns:
        CacheMetadata if the cache exists and is valid, None otherwise.
    """
    path = Path(cache_file)
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cached_at = datetime.fromisoformat(data["cached_at"])
        record_count = data["record_count"]

        return CacheMetadata(
            cached_at=cached_at,
            record_count=record_count,
            cache_file=str(path),
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning("Cache file '%s' is corrupt or malformed: %s", cache_file, exc)
        return None
    except OSError as exc:
        logger.warning("Could not read cache file '%s': %s", cache_file, exc)
        return None


def load_cache(cache_file: str = DEFAULT_CACHE_FILE) -> Optional[List[VinylRecord]]:
    """Load the sorted collection from the local cache file.

    Args:
        cache_file: Path to the cache file.

    Returns:
        List of VinylRecord objects if the cache is valid, None if the
        cache doesn't exist or is corrupt (falls back gracefully).
    """
    path = Path(cache_file)
    if not path.exists():
        logger.debug("No cache file at '%s'.", cache_file)
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict) or "records" not in data:
            logger.warning("Cache file '%s' has unexpected structure.", cache_file)
            return None

        raw_records = data["records"]
        if not isinstance(raw_records, list):
            logger.warning("Cache file '%s': 'records' is not a list.", cache_file)
            return None

        records = [_cache_dict_to_record(r) for r in raw_records]
        logger.info("Loaded %d records from cache '%s'.", len(records), cache_file)
        return records

    except json.JSONDecodeError as exc:
        logger.warning("Cache file '%s' contains invalid JSON: %s", cache_file, exc)
        return None
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Cache file '%s' is malformed: %s", cache_file, exc)
        return None
    except OSError as exc:
        logger.warning("Could not read cache file '%s': %s", cache_file, exc)
        return None


def save_cache(
    records: List[VinylRecord],
    cache_file: str = DEFAULT_CACHE_FILE,
) -> None:
    """Save the sorted collection to the local cache file.

    Args:
        records: Sorted list of VinylRecord objects.
        cache_file: Path to the cache file.
    """
    data = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "records": [_record_to_cache_dict(r) for r in records],
    }

    path = Path(cache_file)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved %d records to cache '%s'.", len(records), cache_file)
    except OSError as exc:
        logger.error("Could not write cache file '%s': %s", cache_file, exc)
