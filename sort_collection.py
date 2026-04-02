#
#   Vinly Collection Sorter - Sort Module
#   MQM 2025-05-21
#
#   This is the module to sequence the collection. The sequencing is first
#   by parsed alphabetically artist and then sequentially by parsed date
#   within artist.
#

#   Standard library imports
import logging
import operator

#   Third party imports

#   Local imports

#
#   Main processing block: sort by artist, sort by date within artist
#

def sort_collection(parsed_collection):
    """Sorting the collection."""
    logging.info("Sorting collection by the parsed fields...")

    sorted_collection = parsed_collection
    sorted_collection.sort(key = operator.attrgetter('sort_artist', 'sort_year'))

    sort_count = 0

    for sorted_item in sorted_collection:
        sort_count += 1
        logging.debug(f"Item #{sort_count} is {sorted_item}.")

    return(sorted_collection)
