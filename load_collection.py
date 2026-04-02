#
#   Vinly Collection Sorter - Load Module
#   MQM 2025-05-21
#
#   This is the module to load the vinyl collection. First implementation
#   will load from Discogs.com. Future enhancements could load from local
#   flat file or other sources.
#

#   Standard library imports
import logging
import time

#   Third party imports
#import discogs_client

#   Local imports
from VinylRecord import VinylRecord
from access_discogs import discogs_login

#
#   Main processing block: log in, download collection
#

def load_collection(VinylCollection):
    """Accessing record collection on Discogs.com."""
    logging.info("Loading collection information...")

    # Log in to Discogs
    discogs_object, discogs_user = discogs_login()

    # Loop through the collection and capture the fields of interest

    for collection_item in discogs_user.collection_folders[0].releases:  # 0 for all items

    #    for collection_item in discogs_user.collection_folders[1].releases:   # 1 for test items
        next_item_discogs_id = collection_item.release.id
        next_item_artist = collection_item.release.artists[0].name # Index 0 for primary artist; i.e. ignore secondary artists
        next_item_artist_id = collection_item.release.artists[0].id # Index 0 for primary artist; i.e. ignore secondary artists
        next_item_title = collection_item.release.title
        next_item_year = collection_item.release.year

        next_item = VinylRecord(next_item_discogs_id,
                                next_item_artist,
                                next_item_artist_id,
                                next_item_title,
                                next_item_year)

        logging.info(f"Loading item #{next_item.import_sequence} {next_item}.")

        VinylCollection.append(next_item)

