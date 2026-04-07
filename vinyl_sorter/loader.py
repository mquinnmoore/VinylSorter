"""Load a vinyl collection from Discogs."""

import logging
from typing import Dict, List, Optional

from .discogs_api import DiscogsAPI
from .models import VinylRecord

logger = logging.getLogger(__name__)


def load_collection(
    api: DiscogsAPI,
    folder_index: int = 0,
    field_ids: Optional[Dict[str, Optional[int]]] = None,
) -> List[VinylRecord]:
    """Fetch all releases from a Discogs collection folder.

    Args:
        api: Authenticated Discogs API session.
        folder_index: Collection folder index (0 = all items).
        field_ids: Mapping of logical name → Discogs field_id for
            reading persisted sort data. Keys: 'sort_artist',
            'sort_year', 'sort_month'.

    Returns:
        List of VinylRecord objects with Discogs source fields populated,
        including any persisted custom field values.
    """
    logger.info("Loading collection from Discogs folder %d…", folder_index)
    field_ids = field_ids or {}
    records: List[VinylRecord] = []

    for item in api.collection_releases(folder_index):
        release = item.release

        # Extract persisted custom field values from notes
        persisted_artist = None
        persisted_year = None
        persisted_month = None
        persisted_compilation = None

        notes = getattr(item, "notes", None) or []
        # Some client versions put notes in .data
        if not notes:
            data = getattr(item, "data", {}) or {}
            notes = data.get("notes", [])

        if notes and field_ids:
            for note in notes:
                fid = note.get("field_id")
                val = (note.get("value") or "").strip()
                if not val:
                    continue

                if fid == field_ids.get("sort_artist"):
                    persisted_artist = val
                elif fid == field_ids.get("sort_year"):
                    try:
                        persisted_year = int(val)
                    except ValueError:
                        logger.warning("Invalid persisted sort_year '%s'", val)
                elif fid == field_ids.get("sort_month"):
                    try:
                        persisted_month = int(val)
                    except ValueError:
                        logger.warning("Invalid persisted sort_month '%s'", val)
                elif fid == field_ids.get("is_compilation"):
                    persisted_compilation = val.lower() in ("yes", "true", "1")

        record = VinylRecord(
            discogs_id=release.id,
            release_artist=release.artists[0].name,
            release_artist_id=release.artists[0].id,
            release_title=release.title,
            release_year=release.year,
            instance_id=getattr(item, "id", -1),
            folder_id=getattr(item, "folder_id", folder_index),
            persisted_sort_artist=persisted_artist,
            persisted_sort_year=persisted_year,
            persisted_sort_month=persisted_month,
            persisted_is_compilation=persisted_compilation,
        )

        if persisted_artist:
            logger.debug(
                "Loaded persisted sort data for %s: artist='%s' year=%s month=%s",
                record, persisted_artist, persisted_year, persisted_month,
            )

        logger.info("Loaded item #%d %s", record.import_number, record)
        records.append(record)

    logger.info("Loaded %d items total.", len(records))
    return records
