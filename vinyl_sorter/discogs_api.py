"""Discogs API access — single session, rate-limited, well-behaved.

This module handles authentication and all Discogs API interactions.
A single DiscogsAPI instance is created at startup and passed to all
functions that need it, avoiding the original per-call re-authentication.
"""

import functools
import logging
import re
import time
from typing import Dict, List, Optional, Tuple

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
        self._token = token
        self._username = self._user.username
        logger.info("Logged into Discogs as %s", self._username)

    @property
    def username(self) -> str:
        """The authenticated Discogs username."""
        return self._username

    # -- Collection -----------------------------------------------------------

    def collection_releases(self, folder_index: int = 0):
        """Iterate over releases in a collection folder."""
        return self._user.collection_folders[folder_index].releases

    # -- Artist ---------------------------------------------------------------

    def lookup_artist_type(self, artist_id: int) -> ArtistType:
        """Determine if an artist is solo or group by checking Discogs members.

        Returns ArtistType.UNKNOWN if the artist ID is not found (e.g.
        compilations, merged or deleted artist entries).
        """
        logger.debug("Looking up Discogs Artist ID: %d", artist_id)
        try:
            artist_info = self._client.artist(artist_id)
            if hasattr(artist_info, "members") and artist_info.members:
                return ArtistType.GROUP
            return ArtistType.SOLO
        except Exception as exc:
            logger.warning("Could not look up artist ID %d: %s", artist_id, exc)
            return ArtistType.UNKNOWN

    # -- Release / Master -----------------------------------------------------

    def lookup_master_fields(self, release_id: int) -> Tuple[bool, str, int, int]:
        """Return (master_exists, master_title, master_year, master_month) for a release.

        Returns (False, "Unknown", -1, 0) if the release or master cannot
        be fetched (e.g. empty API response, network errors).
        """
        try:
            release_info = self._client.release(release_id)
            if release_info.master:
                title = release_info.master.title
                year = release_info.master.year
                # Try to get month from the master's main_release date
                month = 0
                try:
                    main_release = release_info.master.main_release
                    if main_release:
                        date_str = getattr(main_release, 'date_added', '') or ''
                        # Also check data dict for released date
                        data = getattr(main_release, 'data', {}) or {}
                        released = data.get('released', '') or ''
                        if released and '-' in released:
                            parts = released.split('-')
                            if len(parts) >= 2:
                                try:
                                    month = int(parts[1])
                                except (ValueError, IndexError):
                                    pass
                except Exception:
                    pass  # Month extraction is best-effort
                logger.debug("Found master '%s' dated %s-%02d", title, year, month)
                return True, title, year, month
        except Exception as exc:
            logger.warning("Could not look up master for release %d: %s", release_id, exc)

        return False, "Unknown", -1, 0

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

    # -- Custom Fields (persistence) ------------------------------------------

    def get_custom_fields(self) -> List[Dict]:
        """Fetch the user's collection custom field definitions.

        Returns:
            List of field dicts with 'id', 'name', 'type', etc.
        """
        try:
            url = f"https://api.discogs.com/users/{self._username}/collection/fields"
            resp = requests.get(
                url,
                headers={
                    "User-Agent": self._client.user_agent,
                    "Authorization": f"Discogs token={self._token}",
                },
                timeout=30,
            )
            resp.raise_for_status()
            fields = resp.json().get("fields", [])
            logger.info("Found %d custom fields in Discogs collection.", len(fields))
            return fields
        except Exception as exc:
            logger.warning("Could not fetch custom fields: %s", exc)
            return []

    def resolve_field_ids(
        self, field_names: Dict[str, str]
    ) -> Dict[str, Optional[int]]:
        """Map logical field names to Discogs field IDs by matching on name.

        Args:
            field_names: Mapping of logical name → Discogs field label.
                e.g. {"sort_artist": "Sort Artist", "sort_year": "Sort Year"}

        Returns:
            Mapping of logical name → field_id (or None if not found).
        """
        fields = self.get_custom_fields()
        result: Dict[str, Optional[int]] = {k: None for k in field_names}

        for f in fields:
            for logical, label in field_names.items():
                if f.get("name", "").strip().lower() == label.strip().lower():
                    result[logical] = f["id"]
                    logger.debug("Mapped '%s' → field_id %d", label, f["id"])

        return result

    def write_custom_field(
        self,
        folder_id: int,
        release_id: int,
        instance_id: int,
        field_id: int,
        value: str,
    ) -> bool:
        """Write a value to a custom field on a collection instance.

        Args:
            folder_id: Collection folder ID.
            release_id: Discogs release ID.
            instance_id: Collection instance ID.
            field_id: Custom field ID.
            value: Value to write (string).

        Returns:
            True if successful, False otherwise.
        """
        try:
            url = (
                f"https://api.discogs.com/users/{self._username}"
                f"/collection/folders/{folder_id}/releases/{release_id}"
                f"/instances/{instance_id}/fields/{field_id}"
            )
            resp = requests.post(
                url,
                json={"value": str(value)},
                headers={
                    "User-Agent": self._client.user_agent,
                    "Authorization": f"Discogs token={self._token}",
                },
                timeout=30,
            )
            resp.raise_for_status()
            logger.debug(
                "Wrote field %d = '%s' on instance %d", field_id, value, instance_id
            )
            return True
        except Exception as exc:
            logger.warning(
                "Failed to write field %d on instance %d: %s",
                field_id, instance_id, exc,
            )
            return False


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
