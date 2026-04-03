"""Data model for vinyl records."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .constants import ArtistType, INSIGNIFICANT_LEADING_WORDS, LIVE_KEYWORDS

if TYPE_CHECKING:
    from .discogs_api import DiscogsAPI

logger = logging.getLogger(__name__)


@dataclass
class VinylRecord:
    """Central data object representing one vinyl record in the collection.

    Fields prefixed with ``release_`` come directly from Discogs.
    Fields prefixed with ``sort_`` are computed during parsing for
    intelligent sorting.
    """

    # Discogs source fields
    discogs_id: int = -1
    release_artist: str = "None"
    release_artist_id: int = -1
    release_title: str = "None"
    release_year: int = -1

    # Derived fields (populated during parsing)
    release_artist_type: ArtistType = ArtistType.UNKNOWN
    is_live: bool = False
    sort_artist: str = "None"
    sort_year: int = -1
    sort_sequence: int = -1

    # Import order tracking
    import_number: int = field(default=-1, repr=False)

    # Class-level counter
    _import_counter: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        VinylRecord._import_counter += 1
        if self.import_number == -1:
            self.import_number = VinylRecord._import_counter

    def __repr__(self) -> str:
        return f"'{self.release_title}' by {self.release_artist}"

    # ------------------------------------------------------------------
    # Sorting field computation
    # ------------------------------------------------------------------

    def compute_sort_artist(self, api: DiscogsAPI) -> str:
        """Determine the best artist string for alphabetical sorting.

        Solo artists → last name only.
        Groups       → strip leading insignificant words (The, A, An).
        Unknown      → fall back to release artist as-is.
        """
        self.release_artist_type = api.lookup_artist_type(self.release_artist_id)
        logger.debug(
            "Determined %s as type: %s", self.release_artist, self.release_artist_type.value
        )

        if self.release_artist_type == ArtistType.SOLO:
            # Strip title and first name(s) — keep only the last word
            parsed = self.release_artist
            while (space_index := parsed.find(" ")) != -1:
                parsed = parsed[space_index + 1:]
            return parsed

        if self.release_artist_type == ArtistType.GROUP:
            parsed = self.release_artist
            for word in INSIGNIFICANT_LEADING_WORDS:
                parsed = re.sub(rf"^{word}\b\s*", "", parsed)
            return parsed

        logger.info(
            "Couldn't determine %s artist type; defaulting to release artist.",
            self.release_artist,
        )
        return self.release_artist

    def compute_sort_year(self, api: DiscogsAPI) -> int:
        """Determine the best year for chronological sorting.

        Re-releases → original (master) release year.
        Live albums  → performance year extracted from text fields.
        """
        parsed_year = self.release_year
        field_to_check = self.release_title

        # Check for a master release (original release date)
        master_exists, master_title, master_year = api.lookup_master_fields(self.discogs_id)
        if master_exists:
            parsed_year = master_year
            field_to_check = master_title
            logger.debug("Have master title '%s' dated '%s'", master_title, master_year)

        # Check if this is a live recording
        logger.debug("Scanning '%s' for live markers", field_to_check)
        self.is_live = any(
            kw.lower() in field_to_check.lower() for kw in LIVE_KEYWORDS
        )
        logger.debug("Determined '%s' as live recording: %s", self.release_title, self.is_live)

        if self.is_live:
            live_year = api.lookup_live_year(self.discogs_id)
            if live_year is not None and live_year != -1:
                parsed_year = live_year

        return parsed_year
