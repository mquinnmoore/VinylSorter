"""Write computed sort data back to Discogs custom fields."""

import logging
import time
from typing import Dict, List, Optional

from .discogs_api import DiscogsAPI
from .models import VinylRecord

logger = logging.getLogger(__name__)

# Discogs rate limit: 60 requests/minute for authenticated users.
# We add a small delay between writes to stay well within limits.
WRITE_DELAY_SECONDS = 1.1


def write_back_sort_data(
    records: List[VinylRecord],
    api: DiscogsAPI,
    field_ids: Dict[str, Optional[int]],
) -> int:
    """Write computed sort data back to Discogs custom fields.

    Only writes values that have changed (or were newly computed).
    Skips records that already have matching persisted values.

    Args:
        records: List of parsed VinylRecord objects.
        api: Authenticated Discogs API session.
        field_ids: Mapping of logical name → Discogs field_id.

    Returns:
        Number of field writes performed.
    """
    artist_fid = field_ids.get("sort_artist")
    year_fid = field_ids.get("sort_year")
    month_fid = field_ids.get("sort_month")

    if not any([artist_fid, year_fid, month_fid]):
        logger.warning(
            "No custom field IDs configured. Skipping write-back. "
            "Create 'Sort Artist', 'Sort Year', and 'Sort Month' fields "
            "in your Discogs collection settings."
        )
        return 0

    write_count = 0
    skip_count = 0

    for record in records:
        if record.instance_id == -1:
            logger.warning("No instance_id for %s; skipping write-back.", record)
            continue

        writes_needed = []

        # Check if sort_artist needs writing
        if artist_fid and record.sort_artist != record.persisted_sort_artist:
            writes_needed.append((artist_fid, str(record.sort_artist)))

        # Check if sort_year needs writing
        if year_fid and record.sort_year != record.persisted_sort_year:
            writes_needed.append((year_fid, str(record.sort_year)))

        # Check if sort_month needs writing
        current_month = record.sort_month if record.sort_month else 0
        persisted_month = record.persisted_sort_month if record.persisted_sort_month else 0
        if month_fid and current_month != persisted_month:
            writes_needed.append((month_fid, str(current_month)))

        if not writes_needed:
            skip_count += 1
            continue

        for fid, value in writes_needed:
            time.sleep(WRITE_DELAY_SECONDS)
            success = api.write_custom_field(
                folder_id=record.folder_id,
                release_id=record.discogs_id,
                instance_id=record.instance_id,
                field_id=fid,
                value=value,
            )
            if success:
                write_count += 1
            else:
                logger.warning(
                    "Failed to write field %d for %s", fid, record
                )

    logger.info(
        "Write-back complete: %d writes performed, %d records unchanged.",
        write_count, skip_count,
    )
    return write_count
