"""Sort the parsed collection by artist then by year."""

import logging
import operator
from typing import List

from .models import VinylRecord

logger = logging.getLogger(__name__)


def sort_collection(records: List[VinylRecord]) -> List[VinylRecord]:
    """Sort records alphabetically by sort_artist, then chronologically by sort_year.

    Args:
        records: Parsed records with sort_artist and sort_year populated.

    Returns:
        New list of records in sorted order.
    """
    logger.info("Sorting collection by parsed fields…")

    sorted_records = sorted(records, key=operator.attrgetter("sort_artist", "sort_year"))

    for i, record in enumerate(sorted_records, start=1):
        record.sort_sequence = i
        logger.debug("Item #%d: %s", i, record)

    return sorted_records
