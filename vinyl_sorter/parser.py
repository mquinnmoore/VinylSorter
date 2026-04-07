"""Parse sort fields (artist and year) for each record in the collection."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .constants import COMPILATION_ARTISTS
from .discogs_api import DiscogsAPI
from .models import VinylRecord

logger = logging.getLogger(__name__)


def load_aliases(alias_file: Optional[str]) -> Dict[str, str]:
    """Load artist alias overrides from a JSON file.

    The file should be a simple JSON object mapping artist names to sort aliases::

        {
            "The Jerry Garcia Band": "Garcia",
            "Paul McCartney": "Beatles"
        }

    Args:
        alias_file: Path to a JSON alias file, or None to skip.

    Returns:
        Dictionary of artist name → sort alias.
    """
    if not alias_file:
        return {}

    path = Path(alias_file)
    if not path.exists():
        logger.warning("Alias file '%s' not found; skipping aliases.", alias_file)
        return {}

    with open(path, "r", encoding="utf-8") as f:
        aliases = json.load(f)

    logger.info("Loaded %d artist aliases from '%s'.", len(aliases), alias_file)
    return aliases


def parse_collection(
    records: List[VinylRecord],
    api: DiscogsAPI,
    aliases: Optional[Dict[str, str]] = None,
    force_reparse: bool = False,
) -> int:
    """Populate sort_artist, sort_year, and sort_month on each record.

    When persisted values exist on a record (from Discogs custom fields)
    and ``force_reparse`` is False, those values are used directly and
    the expensive API lookups are skipped.

    Records are pre-sorted by release_artist so that consecutive records
    by the same artist can reuse the computed sort_artist (avoiding
    redundant API calls).

    Args:
        records: List of VinylRecord objects to parse (modified in place).
        api: Authenticated Discogs API session.
        aliases: Optional artist alias overrides.
        force_reparse: If True, ignore persisted values and recompute.

    Returns:
        Number of records that required fresh computation (API calls).
    """
    aliases = aliases or {}
    logger.info("Parsing collection artists & dates for sorting…")

    # Pre-sort by artist to group same-artist records together
    records.sort(key=lambda r: r.release_artist)

    last_artist = ""
    last_sort_artist = ""
    last_is_compilation = False
    computed_count = 0

    for record in records:
        logger.info("Parsing %s", record)

        # --- Sort Artist ---
        used_persisted = False

        if (
            not force_reparse
            and record.persisted_sort_artist is not None
        ):
            # Use persisted value from Discogs
            record.sort_artist = record.persisted_sort_artist
            # Use persisted compilation flag if available, otherwise detect
            if record.persisted_is_compilation is not None:
                record.is_compilation = record.persisted_is_compilation
            else:
                record.is_compilation = (
                    record.release_artist in COMPILATION_ARTISTS
                    or record.sort_artist == "Compilation"
                )
            used_persisted = True
            logger.debug(
                "Using persisted sort_artist for '%s': '%s'",
                record.release_artist, record.sort_artist,
            )
        elif record.release_artist in aliases:
            # Check aliases (using cleaned name — parentheticals already stripped)
            record.sort_artist = aliases[record.release_artist]
            record.is_compilation = record.release_artist in COMPILATION_ARTISTS
            logger.debug(
                "Applied alias: '%s' → '%s'", record.release_artist, record.sort_artist
            )
        elif record.release_artist == last_artist:
            # Reuse cached sort_artist for consecutive same-artist records
            record.sort_artist = last_sort_artist
            record.is_compilation = last_is_compilation
        else:
            record.sort_artist = record.compute_sort_artist(api)
            computed_count += 1

        logger.debug("Parsed '%s' → '%s'", record.release_artist, record.sort_artist)

        last_artist = record.release_artist
        last_sort_artist = record.sort_artist
        last_is_compilation = record.is_compilation

        # --- Sort Date ---
        if (
            not force_reparse
            and record.persisted_sort_year is not None
            and used_persisted
        ):
            record.sort_year = record.persisted_sort_year
            record.sort_month = record.persisted_sort_month or 0
            logger.debug(
                "Using persisted sort_date for '%s': %d-%02d",
                record.release_title, record.sort_year, record.sort_month,
            )
        else:
            record.sort_year, record.sort_month = record.compute_sort_date(api)
            if not used_persisted:
                computed_count += 1
            logger.debug(
                "Parsed '%s' as dated %s-%02d",
                record.release_title, record.sort_year, record.sort_month,
            )

    logger.info(
        "Parsing complete. %d records required fresh computation.", computed_count
    )
    return computed_count
