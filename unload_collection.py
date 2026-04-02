#
#   Vinly Collection Sorter - Unload Module
#   MQM 2025-05-21
#
#   This is the module to report out the collection list in sorted order.
#   First release will publish a time-stamped .csv file with headers.
#

#   Standard library imports
import logging
import csv

#   Third party imports

#   Local imports

#
#   Main processing block: loop and print
#

def unload_collection(sorted_collection):
    """Printing out the sorted list."""
    logging.info("Saving the sorted collection information...")

    with open("sorted_vinyl_collection.csv", "w") as collection_csv:
        headers = ["Artist", "Album"]
        csv_writer = csv.DictWriter(collection_csv, fieldnames = headers)
        csv_writer.writeheader()

        for album in sorted_collection:
            csv_writer.writerow({"Artist": album.release_artist, "Album": album.release_title})

