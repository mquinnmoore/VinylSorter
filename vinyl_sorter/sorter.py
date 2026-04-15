"""Sort the parsed collection by artist then by date."""

import logging
import operator
import re
from typing import List

from .constants import INSIGNIFICANT_LEADING_WORDS
from .models import VinylRecord

logger = logging.getLogger(__name__)

# Pre-compile pattern for stripping leading insignificant words from titles
_LEADING_WORD_RE = re.compile(
    rf"^(?:{'|'.join(re.escape(w) for w in INSIGNIFICANT_LEADING_WORDS)})\b\s*",
    re.IGNORECASE,
)


def _sort_title(title: str) -> str:
    """Strip leading insignificant words (The, A, An) for sort purposes."""
    return _LEADING_WORD_RE.sub("", title).lower()


def sort_collection(records: List[VinylRecord]) -> List[VinylRecord]:
    """Sort records: compilations last, then alphabetically by sort_artist,
    then chronologically by sort_year and sort_month.

    Args:
        records: Parsed records with sort fields populated.

    Returns:
        New list of records in sorted order.
    """
    logger.info("Sorting collection by parsed fields…")

    # is_compilation=False (0) sorts before True (1), so compilations land at the end.
    # Non-compilations sort by artist → year → month.
    # Compilations sort alphabetically by album title (stripped of leading
    # "The"/"A"/"An", same rule as group artist names).
    def _sort_key(record: VinylRecord) -> tuple:
        if record.is_compilation:
            return (1, _sort_title(record.release_title), 0, 0)
        return (0, record.sort_artist, record.sort_year, record.sort_month)

    sorted_records = sorted(records, key=_sort_key)

    for i, record in enumerate(sorted_records, start=1):
        record.sort_sequence = i
        logger.debug("Item #%d: %s", i, record)

    return sorted_records
