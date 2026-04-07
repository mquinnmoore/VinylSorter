"""Command-line interface for VinylSorter."""

import argparse

from . import __version__


def parse_args(argv=None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed namespace with all configuration options.
    """
    parser = argparse.ArgumentParser(
        prog="vinyl_sorter",
        description="Sort your vinyl collection by artist and date using Discogs.",
        epilog="Sorting vinyl by genre is a fool's errand.",
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    # Discogs credentials
    creds = parser.add_argument_group("Discogs credentials")
    creds.add_argument(
        "--token",
        default="",
        help="Discogs personal access token (default: $DISCOGS_TOKEN env var)",
    )
    creds.add_argument(
        "--user-agent",
        default="",
        help="User-Agent for Discogs API (default: $DISCOGS_USER_AGENT or 'VinylSorter/2.0')",
    )

    # Collection options
    collection = parser.add_argument_group("Collection options")
    collection.add_argument(
        "--folder",
        type=int,
        default=0,
        help="Discogs collection folder index (default: 0 = all items)",
    )

    # Output options
    output = parser.add_argument_group("Output options")
    output.add_argument(
        "--output", "-o",
        default="sorted_vinyl_collection.csv",
        help="Output file path (default: sorted_vinyl_collection.csv)",
    )
    output.add_argument(
        "--delimiter",
        default=",",
        help="Output field delimiter (default: comma)",
    )

    # Logging
    log = parser.add_argument_group("Logging")
    log.add_argument(
        "--log-file",
        default="vinyl_sorter.log",
        help="Log file path (default: vinyl_sorter.log)",
    )
    log.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    # Aliases
    aliases = parser.add_argument_group("Artist aliases")
    aliases.add_argument(
        "--alias-file",
        default=None,
        help="JSON file mapping artist names to sort aliases",
    )

    # Persistence
    persist = parser.add_argument_group("Persistence (Discogs custom fields)")
    persist.add_argument(
        "--force-reparse",
        action="store_true",
        default=False,
        help="Ignore persisted sort data and recompute everything",
    )
    persist.add_argument(
        "--no-write-back",
        action="store_true",
        default=False,
        help="Don't write computed sort data back to Discogs",
    )
    persist.add_argument(
        "--field-sort-artist",
        default="Sort Artist",
        help="Name of the Discogs custom field for sort artist (default: 'Sort Artist')",
    )
    persist.add_argument(
        "--field-sort-year",
        default="Sort Year",
        help="Name of the Discogs custom field for sort year (default: 'Sort Year')",
    )
    persist.add_argument(
        "--field-sort-month",
        default="Sort Month",
        help="Name of the Discogs custom field for sort month (default: 'Sort Month')",
    )

    return parser.parse_args(argv)
