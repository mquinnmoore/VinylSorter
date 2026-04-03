#
#   Vinly Collection Sorter - Lookup Fields Module
#   MQM 2025-05-23
#
#   This is the module to look up specific fields from an external third
#   party, for first release being MusicBrainz. We are keepign this logic
#   seperated in case there is a better lookup source in the future.
#

#   Standard library imports
import requests
import time

#   Third party imports

#   Local imports
from constants import (SOLO_ARTIST_TYPE, GROUP_ARTIST_TYPE, UNKNOWN_ARTIST_TYPE,
    STUDIO_RECORDING_TYPE, LIVE_RECORDING_TYPE, UNKNOWN_RECORDING_TYPE)

#
#   Rubber meeting road
#

class MusicBrainzClient:
    """Client for interacting with the MusicBrainz API."""

    BASE_URL = "https://musicbrainz.org/ws/2"

    def __init__(self, app_name="vinyl_sorter", version="1.0", contact="m.quinn.moore@mac.com"):
        """
        MusicBrainz requires a proper User-Agent with app name and version.
        """
        self.contact = contact

        # Set up headers for MusicBrainz API
        user_agent = f"{app_name}/{version}"
        if self.contact:
            user_agent += f" ({self.contact})"

        self.headers = {
            "User-Agent": user_agent,
            "Accept": "application/json"
        }

        # Track last request time for rate limiting
        self.last_request_time = 0

    def _make_request(self, endpoint, params=None):
        """Make a rate-limited request to the MusicBrainz API."""
        # Ensure we're not exceeding rate limit (1 request per second)
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < 1:
            sleep_time = 1 - time_since_last_request
            time.sleep(sleep_time)

        response = requests.get(endpoint, headers=self.headers, params=params)
        self.last_request_time = time.time()

        response.raise_for_status()
        return response.json()

    def search_artist(self, artist_name):
        """Search for an artist on MusicBrainz."""
        endpoint = f"{self.BASE_URL}/artist"
        params = {
            "query": artist_name,
            "limit": 10,
            "fmt": "json"
        }

        return self._make_request(endpoint, params)

    def search_release(self, title, artist):
        """Search for a release (album) on MusicBrainz."""
        query = f'release:"{title}"'
        if artist:
            query += f' AND artist:"{artist}"'

        endpoint = f"{self.BASE_URL}/release"
        params = {
            "query": query,
            "limit": 10,
            "fmt": "json"
        }

        return self._make_request(endpoint, params)

    def get_release_info(self, mbid):
        """Get detailed information about a release by its MusicBrainz ID."""
        endpoint = f"{self.BASE_URL}/release/{mbid}"
        params = {
            "inc": "artists+labels+recordings+release-groups",  # Include related entities
            "fmt": "json"
        }

        return self._make_request(endpoint, params)





def lookup_artist_type(artist_name):
    """Determine if an artist is a solo act or group based on MusicBrainz data."""

    # Create the MusicBrainz client
    client = MusicBrainzClient()

    search_results = client.search_artist(artist_name)

    if not search_results.get("artists"):
        return {"error": f"No results found for '{artist_name}'"}

    # Get the first matching artist
    artist_data = search_results["artists"][0]

    # MusicBrainz has specific type values for artists
    # Common types include:
    # - 'Person': Individual artists
    # - 'Group': Bands, ensembles, orchestras
    # - 'Orchestra', 'Choir', etc.: Specific group types
    # - None: Unknown or unspecified

    artist_type = artist_data.get("type")
    mbid = artist_data.get("id")
    name = artist_data.get("name", "")

    # Get more detailed information
    try:
        detailed_info = client.get_artist_info(mbid)
    except Exception:
        detailed_info = artist_data

    # Determine the artist type
    if artist_type == "Person":
        lookup_type = SOLO_ARTIST_TYPE
    elif artist_type in ["Group", "Orchestra", "Choir", "Ensemble"]:
        lookup_type = GROUP_ARTIST_TYPE
    else:
        # Try to infer from other data if type is not specified
        disambiguation = artist_data.get("disambiguation", "").lower()

        if any(term in disambiguation for term in ["band", "group", "ensemble", "orchestra", "duo", "trio", "quartet"]):
            lookup_type = GROUP_ARTIST_TYPE
        elif any(term in disambiguation for term in ["singer", "songwriter", "composer", "solo"]):
            lookup_type = SOLO_ARTIST_TYPE
        else:
            lookup_type = UNKNOWN_ARTIST_TYPE

    return lookup_type


def lookup_recording_type(unparsed_artist, unparsed_title):
    """
    Determine if an album is a live recording.

    MusicBrainz identifies live albums in several ways:
    1. Secondary type "Live" on the release group
    2. Tags containing "live", "concert", etc.
    3. Sometimes in the album title or disambiguation
    """
    lookup_is_live = False
    lookup_type = UNKNOWN_RECORDING_TYPE

    # Create the MusicBrainz client
    client = MusicBrainzClient()

    search_results = client.search_release(unparsed_title, unparsed_artist)

    if not search_results.get("releases"):
        logging.error(f"No results found for release '{unparsed_title}'.")
        return(lookup_is_live)

    # Get the first matching release
    release_data = search_results["releases"][0]
    mbid = release_data.get("id")
    release_group_id = release_data.get("release-group", {}).get("id")

    # Get detailed release information
    try:
        detailed_info = client.get_release_info(mbid)
    except Exception as e:
        return {"error": f"Error fetching release details: {str(e)}"}

    # Get release group information (contains live status)
    if release_group_id:
        try:
            release_group_info = client.get_release_group_info(release_group_id)
        except Exception:
            release_group_info = None
    else:
        release_group_info = None

    # Prepare the result
    result = {
        "title": detailed_info.get("title", unparsed_title),
        "id": mbid,
        "url": f"https://musicbrainz.org/release/{mbid}",
        "artist": unparsed_artist or ", ".join(ac.get("name", "") for ac in detailed_info.get("artist-credit", []))
    }

    # Check if it's a live album
    lookup_is_live = False
    confidence = "Low"
    reasons = []

    # Check release group secondary types for "Live"
    if release_group_info and "secondary-types" in release_group_info:
        if "Live" in release_group_info["secondary-types"]:
            lookup_is_live = True
            confidence = "High"
            reasons.append("MusicBrainz categorizes this as a Live release")

    # Check tags for live indicators
    if release_group_info and "tags" in release_group_info:
        live_tags = [tag for tag in release_group_info["tags"]
                    if any(term in tag["name"].lower() for term in ["live", "concert", "tour", "performance"])]
        if live_tags:
            lookup_is_live = True
            confidence = "High"
            reasons.append(f"Tagged as: {', '.join(tag['name'] for tag in live_tags)}")

    # Check title and disambiguation for live indicators
    title_lower = result["title"].lower()
    disambiguation = detailed_info.get("disambiguation", "").lower()

    live_indicators = ["live", "in concert", "concert", "tour", "recorded live", "live at", "live in"]
    matching_indicators = [ind for ind in live_indicators if ind in title_lower or ind in disambiguation]

    if matching_indicators:
        lookup_is_live = True
        confidence = "Medium" if confidence == "Low" else confidence
        reasons.append(f"Title or description contains: {', '.join(matching_indicators)}")

    return(lookup_is_live)


def lookup_live_date(unparsed_artist, unparsed_title):
    live_year = -1
    live_month = -1

    # Create the MusicBrainz client
    client = MusicBrainzClient()

    return(live_year, live_month)


def lookup_master_date(unparsed_artist, unparsed_title):
    master_year = -1
    master_month = -1

    # Create the MusicBrainz client
    client = MusicBrainzClient()

    return(master_year, master_month)



#
#
#   Below here is MusicBrainz access code generated by Claude and which
#   serves as the basis for everything in this module.
#
#
'''

import requests
import time
import os
from dotenv import load_dotenv

# Load environment variables from .env file (if present)
load_dotenv()

class MusicBrainzClient:
    """Client for interacting with the MusicBrainz API."""
    
    BASE_URL = "https://musicbrainz.org/ws/2"
    
    def __init__(self, app_name="VinylCollectionOrganizer", version="1.0", contact=None):
        """
        Initialize with your application information.
        
        MusicBrainz requires a proper User-Agent with app name and version.
        """
        self.contact = contact or os.getenv("CONTACT_EMAIL", "")
        
        # Set up headers for MusicBrainz API
        user_agent = f"{app_name}/{version}"
        if self.contact:
            user_agent += f" ({self.contact})"
            
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "application/json"
        }
        
        # Track last request time for rate limiting
        self.last_request_time = 0
    
    def _make_request(self, endpoint, params=None):
        """Make a rate-limited request to the MusicBrainz API."""
        # Ensure we're not exceeding rate limit (1 request per second)
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < 1:
            sleep_time = 1 - time_since_last_request
            time.sleep(sleep_time)
        
        response = requests.get(endpoint, headers=self.headers, params=params)
        self.last_request_time = time.time()
        
        response.raise_for_status()
        return response.json()
    
    def search_artist(self, artist_name):
        """Search for an artist on MusicBrainz."""
        endpoint = f"{self.BASE_URL}/artist"
        params = {
            "query": artist_name,
            "limit": 10,
            "fmt": "json"
        }
        
        return self._make_request(endpoint, params)
    
    def get_artist_info(self, mbid):
        """Get detailed information about an artist by their MusicBrainz ID."""
        endpoint = f"{self.BASE_URL}/artist/{mbid}"
        params = {
            "inc": "aliases,url-rels",  # Include aliases and URLs
            "fmt": "json"
        }
        
        return self._make_request(endpoint, params)
    
    def search_release(self, title, artist=None):
        """Search for a release (album) on MusicBrainz."""
        query = f'release:"{title}"'
        if artist:
            query += f' AND artist:"{artist}"'
        
        endpoint = f"{self.BASE_URL}/release"
        params = {
            "query": query,
            "limit": 10,
            "fmt": "json"
        }
        
        return self._make_request(endpoint, params)
    
    def get_release_info(self, mbid):
        """Get detailed information about a release by its MusicBrainz ID."""
        endpoint = f"{self.BASE_URL}/release/{mbid}"
        params = {
            "inc": "artists+labels+recordings+release-groups",  # Include related entities
            "fmt": "json"
        }
        
        return self._make_request(endpoint, params)
    
    def get_release_group_info(self, mbid):
        """Get release group information."""
        endpoint = f"{self.BASE_URL}/release-group/{mbid}"
        params = {
            "inc": "artist-credits+genres+tags",
            "fmt": "json"
        }
        
        return self._make_request(endpoint, params)


def check_artist_type(client, artist_name):
    """Determine if an artist is a solo act or group based on MusicBrainz data."""
    search_results = client.search_artist(artist_name)
    
    if not search_results.get("artists"):
        return {"error": f"No results found for '{artist_name}'"}
    
    # Get the first matching artist
    artist_data = search_results["artists"][0]
    
    # MusicBrainz has specific type values for artists
    # Common types include:
    # - 'Person': Individual artists
    # - 'Group': Bands, ensembles, orchestras
    # - 'Orchestra', 'Choir', etc.: Specific group types
    # - None: Unknown or unspecified
    
    artist_type = artist_data.get("type")
    mbid = artist_data.get("id")
    name = artist_data.get("name", "")
    
    # Get more detailed information
    try:
        detailed_info = client.get_artist_info(mbid)
    except Exception:
        detailed_info = artist_data
        
    # Prepare the result
    result = {
        "name": name,
        "id": mbid,
        "url": f"https://musicbrainz.org/artist/{mbid}",
    }
    
    # Determine the artist type
    if artist_type == "Person":
        lookup_type = "Solo Artist"
    elif artist_type in ["Group", "Orchestra", "Choir", "Ensemble"]:
        lookup_type = "Group"
    else:
        # Try to infer from other data if type is not specified
        disambiguation = artist_data.get("disambiguation", "").lower()
        
        if any(term in disambiguation for term in ["band", "group", "ensemble", "orchestra", "duo", "trio", "quartet"]):
            lookup_type = "Group"
        elif any(term in disambiguation for term in ["singer", "songwriter", "composer", "solo"]):
            lookup_type = "Solo Artist"
        else:
            lookup_type = "Unknown"
            result["notes"] = "Could not determine with confidence if this is a solo artist or group."
    
    # Include disambiguation if available
    if "disambiguation" in artist_data and artist_data["disambiguation"]:
        result["disambiguation"] = artist_data["disambiguation"]
        
    # Include aliases if available
    if "aliases" in detailed_info:
        result["aliases"] = [alias.get("name") for alias in detailed_info.get("aliases", [])]
        
    return result


def check_if_live(client, title, artist=None):
    """
    Determine if an album is a live recording.
    
    MusicBrainz identifies live albums in several ways:
    1. Secondary type "Live" on the release group
    2. Tags containing "live", "concert", etc.
    3. Sometimes in the album title or disambiguation
    """
    search_results = client.search_release(title, artist)
    
    if not search_results.get("releases"):
        return {"error": f"No results found for release '{title}'"}
    
    # Get the first matching release
    release_data = search_results["releases"][0]
    mbid = release_data.get("id")
    release_group_id = release_data.get("release-group", {}).get("id")
    
    # Get detailed release information
    try:
        detailed_info = client.get_release_info(mbid)
    except Exception as e:
        return {"error": f"Error fetching release details: {str(e)}"}
    
    # Get release group information (contains live status)
    if release_group_id:
        try:
            release_group_info = client.get_release_group_info(release_group_id)
        except Exception:
            release_group_info = None
    else:
        release_group_info = None
    
    # Prepare the result
    result = {
        "title": detailed_info.get("title", title),
        "id": mbid,
        "url": f"https://musicbrainz.org/release/{mbid}",
        "artist": artist or ", ".join(ac.get("name", "") for ac in detailed_info.get("artist-credit", []))
    }
    
    # Check if it's a live album
    is_live = False
    confidence = "Low"
    reasons = []
    
    # Check release group secondary types for "Live"
    if release_group_info and "secondary-types" in release_group_info:
        if "Live" in release_group_info["secondary-types"]:
            is_live = True
            confidence = "High"
            reasons.append("MusicBrainz categorizes this as a Live release")
    
    # Check tags for live indicators
    if release_group_info and "tags" in release_group_info:
        live_tags = [tag for tag in release_group_info["tags"] 
                    if any(term in tag["name"].lower() for term in ["live", "concert", "tour", "performance"])]
        if live_tags:
            is_live = True
            confidence = "High"
            reasons.append(f"Tagged as: {', '.join(tag['name'] for tag in live_tags)}")
    
    # Check title and disambiguation for live indicators
    title_lower = result["title"].lower()
    disambiguation = detailed_info.get("disambiguation", "").lower()
    
    live_indicators = ["live", "in concert", "concert", "tour", "recorded live", "live at", "live in"]
    matching_indicators = [ind for ind in live_indicators if ind in title_lower or ind in disambiguation]
    
    if matching_indicators:
        is_live = True
        confidence = "Medium" if confidence == "Low" else confidence
        reasons.append(f"Title or description contains: {', '.join(matching_indicators)}")
    
    # Add live status to result
    result["is_live"] = is_live
    if is_live:
        result["confidence"] = confidence
        result["reasons"] = reasons
    
    # Include additional release information
    if "date" in detailed_info:
        result["release_date"] = detailed_info["date"]
        
    if "country" in detailed_info:
        result["country"] = detailed_info["country"]
        
    if "disambiguation" in detailed_info and detailed_info["disambiguation"]:
        result["disambiguation"] = detailed_info["disambiguation"]
        
    return result


# Example usage
if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Check artist types and live albums using MusicBrainz.")
    parser.add_argument("--contact", "-c", help="Contact email for MusicBrainz API")
    parser.add_argument("--artist", "-a", help="Check if an artist is a solo act or group")
    parser.add_argument("--release", "-r", help="Check if a release is a live recording")
    parser.add_argument("--by", help="Artist name for the release (used with --release)")
    
    args = parser.parse_args()
    
    # Get contact email
    contact = args.contact or os.getenv("CONTACT_EMAIL", "")
    
    if not contact:
        print("Warning: No contact email provided. MusicBrainz recommends including contact info.")
        print("You can provide it with --contact or set CONTACT_EMAIL environment variable.")
    
    # Create the MusicBrainz client
    client = MusicBrainzClient(contact=contact)
    
    # Check artist if requested
    if args.artist:
        print(f"\nChecking artist: {args.artist}")
        try:
            result = check_artist_type(client, args.artist)
            if "error" in result:
                print(f"Error: {result['error']}")
            else:
                print(f"Name: {result['name']}")
                print(f"Type: {result['type']}")
                if "disambiguation" in result:
                    print(f"Description: {result['disambiguation']}")
                if "aliases" in result and result["aliases"]:
                    print(f"Also known as: {', '.join(result['aliases'][:5])}")
                    if len(result["aliases"]) > 5:
                        print(f"  ... and {len(result['aliases']) - 5} more aliases")
                if "notes" in result:
                    print(f"Notes: {result['notes']}")
                print(f"MusicBrainz URL: {result['url']}")
        except Exception as e:
            print(f"Error checking artist: {str(e)}")
    
    # Check release if requested
    if args.release:
        print(f"\nChecking release: {args.release}")
        try:
            result = check_if_live(client, args.release, args.by)
            if "error" in result:
                print(f"Error: {result['error']}")
            else:
                print(f"Title: {result['title']}")
                print(f"Artist: {result['artist']}")
                print(f"Live recording: {'Yes' if result.get('is_live') else 'No'}")
                
                if result.get('is_live'):
                    print(f"Confidence: {result['confidence']}")
                    print(f"Reasons:")
                    for reason in result["reasons"]:
                        print(f"  - {reason}")
                
                if "disambiguation" in result:
                    print(f"Description: {result['disambiguation']}")
                if "release_date" in result:
                    print(f"Released: {result['release_date']}")
                if "country" in result:
                    print(f"Country: {result['country']}")
                print(f"MusicBrainz URL: {result['url']}")
        except Exception as e:
            print(f"Error checking release: {str(e)}")
    
    # If no specific operation was requested, show usage
    if not args.artist and not args.release:
        parser.print_help()

'''
