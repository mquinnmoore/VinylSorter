"""Constants and enumerations for VinylSorter."""

from enum import Enum


class ArtistType(str, Enum):
    """Classification of artist type for sorting purposes."""
    SOLO = "solo"
    GROUP = "group"
    UNKNOWN = "unknown"


class RecordingType(str, Enum):
    """Classification of recording type."""
    STUDIO = "studio"
    LIVE = "live"
    UNKNOWN = "unknown"


# Words to strip from the beginning of group names for sorting
INSIGNIFICANT_LEADING_WORDS = {"The", "A", "An"}

# Keywords that indicate a live recording
LIVE_KEYWORDS = ["live", "recorded live", "live at", "live in", "performed live", "concert", "venue"]

# Artist names that indicate a compilation / various-artists release
COMPILATION_ARTISTS = {"Various", "Various Artists"}

# Pattern matching parenthetical disambiguation numbers from Discogs
# e.g. "Wings (2)" → "Wings"
PARENTHETICAL_NUMBER_RE = r"\s*\(\d+\)\s*$"
