#
#   Vinly Collection Sorter - Parsing Module
#   MQM 2025-05-21
#
#   This is the module to parse the record collection with sortable 
#   embellishments. These include:
#
#       Record Sort Artist
#           - Check the Artist of Record for an entry in the alias table,
#               and use the alias artist if provided
#           - If the artist is a solo artist, use the last name only 
#           - If the artist is a group, strip the name of any leading
#               common identifiers
#
#       Record Sort Date
#           - Use the record's earliest release date, i.e. not the Date of
#               Record when the record is a re-release
#           - If the record is a live recording, use the performace date
#

#   Standard library imports
import logging
import time

#   Third party imports

#   Local imports
from constants import (SOLO_ARTIST_TYPE, GROUP_ARTIST_TYPE, UNKNOWN_ARTIST_TYPE,
    STUDIO_RECORDING_TYPE, LIVE_RECORDING_TYPE, UNKNOWN_RECORDING_TYPE)

#
#   Main processing block: parse artist, parse date
#

def release_artist_sort(an_album):
    return(an_album.release_artist)

def parse_collection(loaded_collection):
    """Creating artist and date fields suitable for sorting."""
    logging.info("Parsing collection artists & dates for sorting...")

    # Do a simple sort based on the given artist name to reduce duplicate processing
    simple_sorted_collection = sorted(loaded_collection, key=release_artist_sort)

    last_artist = ""
    last_sort_artist = ""

    for this_album in simple_sorted_collection:
        logging.info(f"Parsing {this_album}")

        # Re-use the sort artist if this album is by the same artist as the last one.
        # Otherwise figure out the best sorting artist name.
        if this_album.release_artist == last_artist:
            this_album.sort_artist = last_sort_artist
        else:
            this_album.sort_artist = this_album.get_sort_artist()

        logging.debug(f"Parsed '{this_album.release_artist}' to"
                      f" '{this_album.sort_artist}'")

        last_artist = this_album.release_artist       # Save the current artist to
        last_sort_artist = this_album.sort_artist     # compare to the next one

        this_album.sort_year = this_album.get_sort_date()

        logging.debug(f"Parsed '{this_album.release_title}' as dated "
                      f"{this_album.sort_year}.")
