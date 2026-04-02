#
#   Vinly Collection Sorter
#   MQM 2025-05-21
#
#   This is the main level wrapper file for the vinyl collection sorter
#   program. The program follows the outline below, each contained in its
#   own module file:
#
#       load_collection.py
#       parse_collection.py
#       sort_collection.py
#       unload_collection.py
#
#   On first release the sorter will create a list of the collection sorted
#   alphabetically by artist and then by date within each artist. More
#   specifically, these fields are determined as follows:
#
#       Artist
#           - Use user-supplied alias first. i.e. "Garcia" for "The Jerry
#             Garcia Band." The aliases will be read from a file.
#           - Solo acts use the last name only. i.e. "Jones" for "Howard Jones"
#           - Group acts use the name stripped of leading unimportant words
#             i.e. "Beatles" for "The Beatles"
#
#       Date
#           - Use the recording original release date. i.e. replace re-release
#             dates with the master release date.
#           - Use the performace date for live recordings. i.e. replace 
#             the record release date
#
#   Enviornment Requirements
#
#       Ubuntu requires the installation of python3-discogs-client
#

#   Standard library imports
import logging

#   Third party imports

#   Local imports
from load_collection import load_collection, VinylRecord
from parse_collection import parse_collection
from sort_collection import sort_collection
from unload_collection import unload_collection
from constants import (SOLO_ARTIST_TYPE, GROUP_ARTIST_TYPE, UNKNOWN_ARTIST_TYPE,
    STUDIO_RECORDING_TYPE, LIVE_RECORDING_TYPE, UNKNOWN_RECORDING_TYPE)




#
#  Global housekeeping
#

logging.basicConfig(filename='log_vinyl_sorter.log', level=logging.DEBUG,
                    format='%(asctime)s:%(levelname)s:%(message)s')

#
#   Main processing
#
#   Open items:
#       go through the full run last night and look for any parsing errors in artist and master release year
#	real time logging!
#       convert artist names to user-supplied aliases kept in a flat file
#       generic OAuth login
#       save parsed fields back to Discogs
#       read saved parsed fields from Discogs and don't re-process them
#       accept passed parameters (with defaults) for:
#           which Discogs collection folder to import
#           alias file
#           export file
#           export file delimiter
#           Discogs user login information
#           file name for log file
#           debug level for log file
#       show help
#       clean up code and comments - maybe an automated PEP 8 review
#       post to GitHub
#

#
#   Load the collection
#

list_of_records = []

load_collection(list_of_records)

logging.info(f"Loaded {len(list_of_records)} items.")

#
#   Parse the collection for better sorting fields
#

parse_collection(list_of_records)

#
#   Sort the collection smartly by artist and date
#

sorted_list = sort_collection(list_of_records)

#
#   Give the sorted collection back to the user
#

unload_collection(sorted_list)

