"""Load a vinyl collection from Discogs."""

import logging
from typing import List

from .discogs_api import DiscogsAPI
from .models import VinylRecord

logger = logging.getLogger(__name__)


def load_collection(api: DiscogsAPI, folder_index: int = 0) -> List[VinylRecord]:
    """Fetch all releases from a Discogs collection folder.

    Args:
        api: Authenticated Discogs API session.
        folder_index: Collection folder index (0 = all items).

    Returns:
        List of VinylRecord objects with Discogs source fields populated.
    """
    logger.info("Loading collection from Discogs folder %d…", folder_index)
    records: List[VinylRecord] = []

    for item in api.collection_releases(folder_index):
        release = item.release
        record = VinylRecord(
            discogs_id=release.id,
            release_artist=release.artists[0].name,
            release_artist_id=release.artists[0].id,
            release_title=release.title,
            release_year=release.year,
        )
        logger.info("Loaded item #%d %s", record.import_number, record)
        records.append(record)

    logger.info("Loaded %d items total.", len(records))
    return records
