"""Export the sorted collection to a file."""

import csv
import logging
from typing import List

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

    headers = ["Sort #", "Sort Artist", "Artist", "Album", "Sort Year", "Year", "Live"]

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
                "Year": record.release_year,
                "Live": "Yes" if record.is_live else "",
            })

    logger.info("Wrote %d records to '%s'.", len(records), output_file)
