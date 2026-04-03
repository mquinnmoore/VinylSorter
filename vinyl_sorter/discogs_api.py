"""Discogs API access — single session, rate-limited, well-behaved.

This module handles authentication and all Discogs API interactions.
A single DiscogsAPI instance is created at startup and passed to all
functions that need it, avoiding the original per-call re-authentication.
"""

import functools
import logging
import re
import time
from typing import List, Optional, Tuple

import discogs_client
import requests

from .constants import ArtistType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate-limiting decorator
# ---------------------------------------------------------------------------

def rate_limit_handler(func):
    """Decorator that handles Discogs rate limiting with exponential backoff."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.debug("%.1fs backoff before Discogs retry #%d", delay, attempt)
                    time.sleep(delay)

                result = func(*args, **kwargs)

                # Check for rate-limit or server-error responses
                if hasattr(result, "status_code"):
                    if result.status_code == 429:
                        if attempt < max_retries:
                            retry_after = int(result.headers.get("Retry-After", base_delay * 2))
                            logger.warning("Rate-limited by Discogs; waiting %ds", retry_after)
                            time.sleep(retry_after)
                            continue
                        logger.error("Max retries reached for rate limiting")
                        return result
                    if result.status_code in {500, 502, 503, 504} and attempt < max_retries:
                        logger.warning("Discogs error %d, retrying…", result.status_code)
                        continue

                return result

            except requests.exceptions.RequestException as exc:
                if attempt < max_retries:
                    logger.warning("Request failed: %s, retrying…", exc)
                    continue
                logger.error("Max retries reached: %s", exc)
                raise

        return result  # type: ignore[possibly-undefined]

    return wrapper


# ---------------------------------------------------------------------------
# Main API class
# ---------------------------------------------------------------------------

class DiscogsAPI:
    """Single authenticated session for all Discogs interactions."""

    def __init__(self, user_agent: str, token: str) -> None:
        self._client = discogs_client.Client(user_agent, user_token=token)
        self._user = self._client.identity()
        logger.info("Logged into Discogs as %s", self._user)

    # -- Collection -----------------------------------------------------------

    def collection_releases(self, folder_index: int = 0):
        """Iterate over releases in a collection folder."""
        return self._user.collection_folders[folder_index].releases

    # -- Artist ---------------------------------------------------------------

    def lookup_artist_type(self, artist_id: int) -> ArtistType:
        """Determine if an artist is solo or group by checking Discogs members."""
        logger.debug("Looking up Discogs Artist ID: %d", artist_id)
        artist_info = self._client.artist(artist_id)

        if hasattr(artist_info, "members") and artist_info.members:
            return ArtistType.GROUP
        return ArtistType.SOLO

    # -- Release / Master -----------------------------------------------------

    def lookup_master_fields(self, release_id: int) -> Tuple[bool, str, int]:
        """Return (master_exists, master_title, master_year) for a release."""
        release_info = self._client.release(release_id)

        if release_info.master:
            title = release_info.master.title
            year = release_info.master.year
            logger.debug("Found master '%s' dated %s", title, year)
            return True, title, year

        return False, "Unknown", -1

    def lookup_live_year(self, release_id: int) -> Optional[int]:
        """Search release and master text fields for a live-performance year."""
        try:
            release = self._client.release(release_id)
            all_dates: List[str] = []

            # Check release title and notes
            for field_name in ("title", "notes"):
                text = getattr(release, field_name, "") or ""
                dates = _extract_dates(text)
                if dates:
                    all_dates.extend(dates)
                    logger.debug("Found dates in release %s: %s", field_name, dates)

            # Check master title and notes
            master = getattr(release, "master", None)
            if master:
                for field_name in ("title", "notes"):
                    text = getattr(master, field_name, "") or ""
                    dates = _extract_dates(text)
                    if dates:
                        all_dates.extend(dates)
                        logger.debug("Found dates in master %s: %s", field_name, dates)

            years = _extract_years_from_dates(all_dates)
            if years:
                earliest = min(years)
                logger.debug("Earliest year found: %d", earliest)
                return earliest

            logger.debug("No dates found for release %d", release_id)
            return None

        except Exception as exc:
            logger.error("Error processing release %d: %s", release_id, exc)
            return None


# ---------------------------------------------------------------------------
# Date extraction helpers (preserved from original lookup_fields.py)
# ---------------------------------------------------------------------------

def _extract_dates(text: str) -> List[str]:
    """Extract potential date strings from free text using multiple patterns."""
    if not text:
        return []

    dates_found: List[str] = []

    patterns = [
        # Full dates
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\b\d{1,2}/\d{1,2}/\d{4}\b",
        r"\b\d{1,2}-\d{1,2}-\d{4}\b",
        r"\b(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4}\b",
        r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{4}\b",
        # Month/Year
        r"\b(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{4}\b",
        r"\b\d{1,2}/\d{4}\b",
        # Year only (1950–2049)
        r"\b(19[5-9]\d|20[0-4]\d)\b",
        # Dotted dates (1.3.73, 01.03.1973)
        r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b",
        # Short dashed dates (1-3-73)
        r"\b\d{1,2}-\d{1,2}-\d{2}\b",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            item = match[0] if isinstance(match, tuple) else match
            dates_found.append(item)

    return dates_found


def _extract_years_from_dates(date_strings: List[str]) -> List[int]:
    """Pull 4-digit years (1950–2049) from a list of date strings."""
    years: List[int] = []

    for date_str in date_strings:
        for year_str in re.findall(r"\b(19[5-9]\d|20[0-4]\d)\b", str(date_str)):
            year = int(year_str)
            if year not in years:
                years.append(year)

    return sorted(years)
