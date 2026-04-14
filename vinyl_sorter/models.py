"""Data model for vinyl records."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Tuple

from .constants import (
    ArtistType,
    COMPILATION_ARTISTS,
    INSIGNIFICANT_LEADING_WORDS,
    LIVE_KEYWORDS,
    PARENTHETICAL_NUMBER_RE,
)

if TYPE_CHECKING:
    from .discogs_api import DiscogsAPI

logger = logging.getLogger(__name__)


def clean_artist_name(name: str) -> str:
    """Strip Discogs disambiguation suffixes like '(2)' from artist names.

    Args:
        name: Raw artist name from Discogs.

    Returns:
        Cleaned artist name.
    """
    return re.sub(PARENTHETICAL_NUMBER_RE, "", name).strip()


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

    # Discogs collection instance fields (needed for write-back)
    instance_id: int = -1
    folder_id: int = 0

    # Persisted values from Discogs custom fields (None = not yet stored)
    persisted_sort_artist: Optional[str] = None
    persisted_sort_year: Optional[int] = None
    persisted_sort_month: Optional[int] = None
    persisted_is_compilation: Optional[bool] = None

    # Derived fields (populated during parsing)
    release_artist_type: ArtistType = ArtistType.UNKNOWN
    is_compilation: bool = False
    is_live: bool = False
    sort_artist: str = "None"
    sort_year: int = -1
    sort_month: int = 0  # 0 = unknown; 1–12 = Jan–Dec
    sort_sequence: int = -1

    # Import order tracking
    import_number: int = field(default=-1, repr=False)

    # Class-level counter
    _import_counter: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        VinylRecord._import_counter += 1
        if self.import_number == -1:
            self.import_number = VinylRecord._import_counter
        # Clean parenthetical numbers from artist name on load (#6)
        self.release_artist = clean_artist_name(self.release_artist)

    def __repr__(self) -> str:
        return f"'{self.release_title}' by {self.release_artist}"

    # ------------------------------------------------------------------
    # Sorting field computation
    # ------------------------------------------------------------------

    def compute_sort_artist(self, api: DiscogsAPI) -> str:
        """Determine the best artist string for alphabetical sorting.

        Compilations → flagged and sorted to the end.
        Solo artists → last name only.
        Groups       → strip leading insignificant words (The, A, An).
        Unknown      → fall back to release artist as-is.
        """
        # Check for compilations first
        if self.release_artist in COMPILATION_ARTISTS:
            self.is_compilation = True
            logger.debug("Detected '%s' as a compilation.", self.release_title)
            return "Compilation"

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

    def compute_sort_date(self, api: DiscogsAPI) -> Tuple[int, int]:
        """Determine the best year and month for chronological sorting.

        Re-releases → original (master) release year/month.
        Live albums  → performance year extracted from text fields.

        Returns:
            (year, month) tuple. Month is 0 if unknown.
        """
        parsed_year = self.release_year
        parsed_month = 0
        field_to_check = self.release_title

        # Check for a master release (original release date)
        master_exists, master_title, master_year, master_month, notes = api.lookup_master_fields(
            self.discogs_id
        )
        if master_exists:
            parsed_year = master_year
            parsed_month = master_month
            field_to_check = master_title
            logger.debug("Have master title '%s' dated %s-%02d", master_title, master_year, master_month)

        # Check if this is a live recording (scan title AND notes)
        # Use word-boundary matching to avoid false positives like
        # "Avenue" matching "venue" or "delivered" matching "live".
        text_to_scan = f"{field_to_check}\n{notes}".strip()
        logger.debug("Scanning title + notes for live markers on '%s'", self.release_title)
        self.is_live = any(
            re.search(rf"\b{re.escape(kw)}\b", text_to_scan, re.IGNORECASE)
            for kw in LIVE_KEYWORDS
        )
        logger.debug("Determined '%s' as live recording: %s", self.release_title, self.is_live)

        if self.is_live:
            live_year = api.lookup_live_year(self.discogs_id)
            if live_year is not None and live_year != -1:
                parsed_year = live_year
                parsed_month = 0  # Live year extraction doesn't give us month

        return parsed_year, parsed_month
