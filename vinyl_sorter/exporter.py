"""Export the sorted collection to a file."""

import csv
import json
import logging
from typing import Any, Dict, List

from .models import VinylRecord

logger = logging.getLogger(__name__)


def export_collection(
    records: List[VinylRecord],
    output_file: str = "sorted_vinyl_collection.csv",
    delimiter: str = ",",
) -> None:
    """Write the sorted collection to a delimited file.

    Args:
        records: Sorted list of VinylRecord objects.
        output_file: Path to the output file.
        delimiter: Field delimiter character.
    """
    logger.info("Saving sorted collection to '%s'…", output_file)

    headers = [
        "Sort #", "Sort Artist", "Artist", "Album",
        "Sort Year", "Sort Month", "Year", "Live", "Compilation",
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=delimiter)
        writer.writeheader()

        for record in records:
            writer.writerow({
                "Sort #": record.sort_sequence,
                "Sort Artist": record.sort_artist,
                "Artist": record.release_artist,
                "Album": record.release_title,
                "Sort Year": record.sort_year,
                "Sort Month": record.sort_month if record.sort_month else "",
                "Year": record.release_year,
                "Live": "Yes" if record.is_live else "",
                "Compilation": "Yes" if record.is_compilation else "",
            })

    logger.info("Wrote %d records to '%s'.", len(records), output_file)


def record_to_dict(record: VinylRecord) -> Dict[str, Any]:
    """Convert a VinylRecord to a JSON-serializable dictionary.

    This is the canonical schema used by both JSON export and the API.
    Includes all fields needed for display; see ``cache._record_to_cache_dict()``
    for the full-fidelity version used by the local cache.

    Args:
        record: A VinylRecord object.

    Returns:
        Dictionary with all record fields.
    """
    return {
        "discogs_id": record.discogs_id,
        "sort_sequence": record.sort_sequence,
        "release_artist": record.release_artist,
        "release_artist_id": record.release_artist_id,
        "sort_artist": record.sort_artist,
        "release_title": record.release_title,
        "release_year": record.release_year,
        "sort_year": record.sort_year,
        "sort_month": record.sort_month,
        "is_compilation": record.is_compilation,
        "is_live": record.is_live,
        "cover_image_url": record.cover_image_url,
        "thumb_url": record.thumb_url,
        "instance_id": record.instance_id,
        "folder_id": record.folder_id,
        "import_number": record.import_number,
    }


def export_collection_json(records: List[VinylRecord]) -> List[Dict[str, Any]]:
    """Convert the sorted collection to a list of JSON-serializable dicts.

    Uses the same schema the API returns.

    Args:
        records: Sorted list of VinylRecord objects.

    Returns:
        List of dictionaries, one per record.
    """
    return [record_to_dict(r) for r in records]


def export_collection_json_file(
    records: List[VinylRecord],
    output_file: str = "sorted_vinyl_collection.json",
) -> None:
    """Write the sorted collection to a JSON file.

    Args:
        records: Sorted list of VinylRecord objects.
        output_file: Path to the output file.
    """
    logger.info("Saving sorted collection to '%s' (JSON)…", output_file)
    data = export_collection_json(records)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Wrote %d records to '%s'.", len(records), output_file)
