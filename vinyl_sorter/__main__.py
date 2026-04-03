"""Entry point for `python -m vinyl_sorter`."""

import logging
import sys

from .cli import parse_args
from .config import Config
from .discogs_api import DiscogsAPI
from .exporter import export_collection
from .loader import load_collection
from .parser import load_aliases, parse_collection
from .sorter import sort_collection


def main() -> None:
    """Run the full VinylSorter pipeline: load → parse → sort → export."""
    args = parse_args()
    config = Config.from_args(args)

    # Set up logging
    logging.basicConfig(
        filename=config.log_file,
        level=getattr(logging, config.log_level),
        format="%(asctime)s:%(levelname)s:%(name)s:%(message)s",
    )
    logger = logging.getLogger(__name__)

    # Validate credentials
    if not config.discogs_token:
        print(
            "Error: No Discogs token provided.\n"
            "Use --token or set the DISCOGS_TOKEN environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Connect to Discogs (single session for the entire run)
    logger.info("Starting VinylSorter…")
    api = DiscogsAPI(user_agent=config.discogs_user_agent, token=config.discogs_token)

    # Load
    records = load_collection(api, folder_index=config.folder_index)
    logger.info("Loaded %d records.", len(records))

    # Parse
    aliases = load_aliases(config.alias_file)
    parse_collection(records, api, aliases=aliases)

    # Sort
    sorted_records = sort_collection(records)

    # Export
    export_collection(sorted_records, output_file=config.output_file, delimiter=config.delimiter)

    print(f"Done! {len(sorted_records)} records sorted → {config.output_file}")


if __name__ == "__main__":
    main()
