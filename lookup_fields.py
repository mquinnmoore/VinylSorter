#
#   Vinly Collection Sorter - Lookup Fields Module
#   MQM 2025-05-23
#
#   This is the module to look up specific data points on an individual album.
#   Note that we had originally intended to use MusicBrainz as the source of
#   this information but found too many discrepancies between the MusicBrainz
#   crowd-sourced data and the Discogs crowd-sourced data. Since we are keeping
#   the collection itself in Discogs we're going to look there for more details.
#   We are still keeping this logic modularized in case we find better ways to
#   this later.
#

#   Standard library imports
import logging
import re
from typing import Dict, List, Optional, Tuple

#   Third party imports

#   Local imports
from access_discogs import discogs_login
from constants import (SOLO_ARTIST_TYPE, GROUP_ARTIST_TYPE, UNKNOWN_ARTIST_TYPE,
    STUDIO_RECORDING_TYPE, LIVE_RECORDING_TYPE, UNKNOWN_RECORDING_TYPE)

#
#   Rubber meeting road
#


def lookup_artist_type(discogs_artist_id):
    """Determine if an artist is a solo act or group based on whether the artist
    is listed in Discogs has having any members or not. This seems to be the most
    direct and accurate way to tell for initial release.
    """
    logging.debug(f"Looking up Discogs Artist ID: {discogs_artist_id}.")

    discogs_object, discogs_user = discogs_login()
    artist_full_info = discogs_object.artist(discogs_artist_id)

    if hasattr(artist_full_info, 'members') and artist_full_info.members:
        lookup_type = GROUP_ARTIST_TYPE
    else:
        lookup_type = SOLO_ARTIST_TYPE

    return lookup_type


def lookup_master_fields(discogs_release_id):
    """ Find the master release year in Discogs."""
    master_exists = False
    master_title = "Unknown"
    master_year = -1

    discogs_object, discogs_user = discogs_login()
    release_full_info = discogs_object.release(discogs_release_id)

    if release_full_info.master:
        master_exists = True
        master_title = release_full_info.master.title
        master_year = release_full_info.master.year
        logging.debug(f"Found master '{master_title}' dated {master_year}.")

    return(master_exists, master_title, master_year)


def lookup_live_year(discogs_release_id):
    """
    Claude helped write this function to check if a live recording's date is
    mentioned in release or master release text fields.
    """

    discogs_object, _ = discogs_login()

    try:
        # Get release details
        release = discogs_object.release(discogs_release_id)

        # Collect all date mentions
        all_dates = []

        # Check release title
        release_title = getattr(release, 'title', '')
        title_dates = extract_dates(release_title)
        if title_dates:
            all_dates.extend(title_dates)
            logging.debug(f"Found dates in release title: {title_dates}")

        # Check release notes
        release_notes = getattr(release, 'notes', '')
        notes_dates = extract_dates(release_notes)
        if notes_dates:
            all_dates.extend(notes_dates)
            logging.debug(f"Found dates in release notes: {notes_dates}")

        # Get master release details if available
        master = getattr(release, 'master', None)
        if master:
            try:
                # Check master title
                master_title = getattr(master, 'title', '')
                master_title_dates = extract_dates(master_title)
                if master_title_dates:
                    all_dates.extend(master_title_dates)
                    logging.debug(f"Found dates in master title: {master_title_dates}")

                # Check master notes
                master_notes = getattr(master, 'notes', '')
                master_notes_dates = extract_dates(master_notes)
                if master_notes_dates:
                    all_dates.extend(master_notes_dates)
                    logging.debug(f"Found dates in master notes: {master_notes_dates}")

            except Exception as e:
                logging.warning(f"Error accessing master release: {e}")

        # Extract years from all found dates and find the earliest
        years = extract_years_from_dates(all_dates)
        if years:
            earliest_year = min(years)
            logging.debug(f"Earliest year found: {earliest_year}")
            return earliest_year
        else:
            logging.debug(f"No dates found for release {discogs_release_id}")
            return None

    except Exception as e:
        logging.error(f"Error processing release {discogs_release_id}: {e}")
        return None

def extract_dates(text: str) -> List[str]:
    """
    Extract potential dates from text using various patterns

    Returns list of date strings found
    """
    if not text:
        return []

    dates_found = []

    # Various date patterns to look for
    patterns = [
        # Full dates: 1973-03-01, 03/01/1973, March 1, 1973
        r'\b\d{4}-\d{1,2}-\d{1,2}\b',
        r'\b\d{1,2}/\d{1,2}/\d{4}\b',
        r'\b\d{1,2}-\d{1,2}-\d{4}\b',
        r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',

        # Month/Year: March 1973, 03/1973
        r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
        r'\b\d{1,2}/\d{4}\b',

        # Year only (4 digits, likely years for live recordings)
        r'\b(19[5-9]\d|20[0-4]\d)\b',

        # Common live recording date formats
        r'\b\d{1,2}\.\d{1,2}\.\d{2,4}\b',  # 1.3.73, 01.03.1973
        r'\b\d{1,2}-\d{1,2}-\d{2}\b',      # 1-3-73

        # Live recording specific patterns
        r'Live\s+at\s+.*?\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',  # "Live at venue 3/1/73"
        r'Recorded\s+.*?(\d{4})',  # "Recorded March 1973"
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if isinstance(matches[0] if matches else None, tuple):
            # For patterns with groups, take the first group
            dates_found.extend([match[0] if isinstance(match, tuple) else match for match in matches])
        else:
            dates_found.extend(matches)

    return dates_found

def extract_years_from_dates(date_strings: List[str]) -> List[int]:
    """
    Extract 4-digit years from a list of date strings

    Args:
        date_strings: List of date strings in various formats

    Returns:
        List of years as integers
    """
    years = []

    for date_str in date_strings:
        # Look for 4-digit years (1950-2049)
        year_matches = re.findall(r'\b(19[5-9]\d|20[0-4]\d)\b', str(date_str))
        for year_str in year_matches:
            try:
                year = int(year_str)
                if year not in years:  # Avoid duplicates
                    years.append(year)
            except ValueError:
                continue

    return sorted(years)


