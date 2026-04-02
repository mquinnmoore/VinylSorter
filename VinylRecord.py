#
#   Vinly Collection Sorter - VinylRecord Object Module
#   MQM 2025-05-23
#
#   This is the module holding the class and method definitions for the
#   ubiquitious VinylRecord object.
#

#   Standard library imports
import logging
import re

#   Third party imports

#   Local imports
from constants import (SOLO_ARTIST_TYPE, GROUP_ARTIST_TYPE, UNKNOWN_ARTIST_TYPE,
    STUDIO_RECORDING_TYPE, LIVE_RECORDING_TYPE, UNKNOWN_RECORDING_TYPE)
from lookup_fields import (lookup_artist_type, lookup_master_fields, lookup_live_year)

#
#   Heavy lifting section
#

class VinylRecord:
    """ This is the central object to store and process vinyl records"""

    import_sequence = 0                         # Order of importing

    def __init__(self,
                 discogs_id = -1,               # unique identifier used by Discogs DB
                 release_artist = "None",       # Common artist name
                 release_artist_id = -1,        # Common artist name
                 release_title = "None",        # Record title
                 release_year = -1,             # Record release; might be new re-issue
                 release_artist_type = "None",  # Solo, Group, etc. to be sourced from MusicBrainz
                 is_live = False,               # Flag for live recording to be sourced from MusicBrainz
                 sort_artist = "None",          # Holder for parsed sort name
                 sort_year = -1,                # Holder for parsed sort date
                 sort_sequence = -1             # Holder for determined sort place
                 ):

                 self.discogs_id = discogs_id
                 self.release_artist = release_artist
                 self.release_artist_id = release_artist_id
                 self.release_title = release_title
                 self.release_year = release_year
                 self.release_artist_type = release_artist_type
                 self.is_live = is_live
                 self.sort_artist = sort_artist
                 self.sort_year = sort_year
                 self.sort_sequence = sort_sequence

                 VinylRecord.import_sequence += 1   # Increment the number of records while loading


    def __repr__(self):
        return(f"'{self.release_title}' by {self.release_artist}")


    def get_sort_artist(self):
        """ Transform the artist as given into the proper sorting version
        Solo artists -> last name only
        Group artists -> strip leading unnecessary words
        """
        parsed_sort_artist = "Unknown"
        self.release_artist_type = UNKNOWN_ARTIST_TYPE

        self.release_artist_type = lookup_artist_type(self.release_artist_id)
        logging.debug(f"Determined {self.release_artist} as type: {self.release_artist_type}.")

        if self.release_artist_type == SOLO_ARTIST_TYPE:
            parsed_sort_artist = self.release_artist
            # Strip  title and first name (i.e. any leading words followed by a space), if any
            while (space_index := parsed_sort_artist.find(' ')) != -1:
                parsed_sort_artist = parsed_sort_artist[space_index + 1:]
        elif self.release_artist_type == GROUP_ARTIST_TYPE:
            parsed_sort_artist = self.release_artist
            parsed_sort_artist = re.sub(r'^The\b\s*', '', parsed_sort_artist)
            parsed_sort_artist = re.sub(r'^A\b\s*', '', parsed_sort_artist)
            parsed_sort_artist = re.sub(r'^An\b\s*', '', parsed_sort_artist)
        else:
            logging.info(f"Couldn't use {self.release_artist} artist type, defauting to release artist.")
            parsed_sort_artist = self.release_artist

        return(parsed_sort_artist)


    def get_sort_date(self):
        """ Transform the release date as given into the proper sorting version
        Re-releases -> original release date
        Live recordings -> performance date
        """
        parsed_sort_year = self.release_year    # Default to the date already on the release
        field_to_check = self.release_title    # Default to checking the release title for live indicators

        # Not all releases have master records
        master_exists, master_title, master_year = lookup_master_fields(self.discogs_id)  # noqa: F821
        if master_exists:
            parsed_sort_year = master_year
            field_to_check = master_title
            logging.debug(f"Have master title '{master_title}' dated '{master_year}'.")

        logging.debug(f"Scanning '{field_to_check}' for live markers.")

        keywords = ['live', 'recorded at', 'concert', 'venue']

        if any(keyword.lower() in field_to_check.lower() for keyword in keywords):
            self.is_live = True
        else:
            self.is_live = False

        logging.debug(f"Determined '{self.release_title}' as live recording"
            f" is {self.is_live}.")

        if self.is_live:        # Try to strip a year out of the title or notes
            live_year = lookup_live_year(self.discogs_id)

            if live_year != -1 and live_year:
                parsed_sort_year = live_year

        return(parsed_sort_year)



