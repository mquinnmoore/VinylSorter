"""Entry point for `python -m vinyl_sorter`."""

import logging
import sys

from .cli import parse_args
from .config import Config
from .discogs_api import DiscogsAPI
from .exporter import export_collection
from .loader import load_collection
from .parser import load_aliases, parse_collection
from .persistence import write_back_sort_data
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

    # Resolve custom field IDs for persistence
    field_ids = api.resolve_field_ids({
        "sort_artist": config.field_sort_artist,
        "sort_year": config.field_sort_year,
        "sort_month": config.field_sort_month,
        "is_compilation": config.field_is_compilation,
    })

    has_fields = any(v is not None for v in field_ids.values())
    field_name_map = {
        "sort_artist": config.field_sort_artist,
        "sort_year": config.field_sort_year,
        "sort_month": config.field_sort_month,
        "is_compilation": config.field_is_compilation,
    }
    if has_fields:
        found = [f"{k} ('{field_name_map[k]}' → field {v})" for k, v in field_ids.items() if v is not None]
        missing = [f"{k} (expected '{field_name_map[k]}')" for k, v in field_ids.items() if v is None]
        print(f"\u2705 Custom fields found: {', '.join(found)}")
        if missing:
            print(f"\u26a0\ufe0f  Custom fields not found: {', '.join(missing)}")
            print("  Persistence will be skipped for missing fields.")
            print("  Check your Discogs collection settings or use --field-sort-* flags.")
    else:
        print(
            "\u26a0\ufe0f  No custom fields found in Discogs. Sort data will not be persisted.\n"
            "  To enable persistence, create these textarea fields in your\n"
            f"  Discogs collection settings (https://www.discogs.com/settings/collection):\n"
            f"    - '{config.field_sort_artist}'\n"
            f"    - '{config.field_sort_year}'\n"
            f"    - '{config.field_sort_month}'\n"
            f"    - '{config.field_is_compilation}'\n"
            "  Field names must match exactly (case-insensitive).\n"
            "  Or use --field-* flags to match your existing field names."
        )

    # Load (reads persisted custom field values if available)
    records = load_collection(
        api,
        folder_index=config.folder_index,
        field_ids=field_ids if has_fields else None,
    )
    logger.info("Loaded %d records.", len(records))

    # Parse (skips API lookups when persisted values exist)
    aliases = load_aliases(config.alias_file)
    computed_count = parse_collection(
        records, api, aliases=aliases, force_reparse=config.force_reparse,
    )

    if config.force_reparse:
        print(f"Force-reparsed all {len(records)} records.")
    elif computed_count > 0:
        print(f"Computed sort data for {computed_count} records (others used persisted values).")
    else:
        print("All records had persisted sort data — no API lookups needed!")

    # Sort
    sorted_records = sort_collection(records)

    # Export
    export_collection(sorted_records, output_file=config.output_file, delimiter=config.delimiter)

    # Write back (unless --no-write-back)
    if has_fields and not config.no_write_back:
        print("Writing sort data back to Discogs…")
        write_count = write_back_sort_data(sorted_records, api, field_ids)
        if write_count > 0:
            print(f"Updated {write_count} custom field values in Discogs.")
        else:
            print("No changes to write back.")
    elif config.no_write_back:
        print("Skipping write-back (--no-write-back).")

    print(f"Done! {len(sorted_records)} records sorted → {config.output_file}")


if __name__ == "__main__":
    main()
