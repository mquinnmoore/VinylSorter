"""Entry point for `python -m vinyl_sorter`."""

import logging
import sys

from .cache import get_cache_metadata, load_cache, save_cache
from .cli import parse_args
from .config import Config
from .discogs_api import DiscogsAPI
from .exporter import export_collection, export_collection_json_file
from .loader import load_collection
from .parser import load_aliases, parse_collection
from .persistence import write_back_sort_data
from .sorter import sort_collection


def _run_full_pipeline(
    api: DiscogsAPI,
    config: Config,
    field_ids: dict,
    has_fields: bool,
) -> list:
    """Run the full Discogs load → parse → sort pipeline.

    Returns:
        Sorted list of VinylRecord objects.
    """
    logger = logging.getLogger(__name__)

    records = load_collection(
        api,
        folder_index=config.folder_index,
        field_ids=field_ids if has_fields else None,
    )
    logger.info("Loaded %d records.", len(records))

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

    return sort_collection(records)


def _resolve_fields(api: DiscogsAPI, config: Config) -> tuple:
    """Resolve custom field IDs and print status.

    Returns:
        (field_ids, has_fields) tuple.
    """
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
        found = [
            f"{k} ('{field_name_map[k]}' → field {v})"
            for k, v in field_ids.items() if v is not None
        ]
        missing = [
            f"{k} (expected '{field_name_map[k]}')"
            for k, v in field_ids.items() if v is None
        ]
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

    return field_ids, has_fields


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
    field_ids, has_fields = _resolve_fields(api, config)

    # ------------------------------------------------------------------
    # Smart startup: try local cache first, then fall back to full pipeline
    # ------------------------------------------------------------------
    use_cache = not config.no_cache
    sorted_records = None
    ran_pipeline = False

    if use_cache and not config.refresh:
        meta = get_cache_metadata(config.cache_file)

        if meta is not None:
            # Cache exists — do a lightweight count check against Discogs
            try:
                discogs_count = api.collection_count(config.folder_index)
            except Exception as exc:
                logger.warning("Could not check Discogs collection count: %s", exc)
                # If count check fails, trust the cache
                discogs_count = meta.record_count

            if discogs_count == meta.record_count:
                # Count matches — load from cache
                cached_records = load_cache(config.cache_file)
                if cached_records is not None:
                    sorted_records = cached_records
                    print(
                        f"Loaded {len(sorted_records)} records from local cache "
                        f"(cached {meta.cached_ago}). "
                        f"Discogs count matches — cache is current."
                    )
                else:
                    # Cache file was corrupt despite valid metadata
                    print("Cache file is corrupt — falling back to full Discogs reload…")
            else:
                print(
                    f"Cache has {meta.record_count} records but Discogs has "
                    f"{discogs_count} — refreshing from Discogs…"
                )
        else:
            print("No local cache found — loading from Discogs…")
    elif config.refresh:
        print("Forced refresh — loading from Discogs…")
    # else: --no-cache — original behavior, no messages about cache

    # If cache didn't provide records, run the full pipeline
    if sorted_records is None:
        sorted_records = _run_full_pipeline(api, config, field_ids, has_fields)
        ran_pipeline = True

        # Save cache (unless --no-cache)
        if use_cache:
            save_cache(sorted_records, config.cache_file)
            print(f"Saved {len(sorted_records)} records to local cache.")

    # Serve mode: start the FastAPI server with the sorted collection
    if config.serve:
        print(f"Starting API server on port {config.port}…")
        from .api import create_app
        import uvicorn

        app = create_app(sorted_records, config=config)
        uvicorn.run(app, host="0.0.0.0", port=config.port)
        return  # uvicorn.run blocks; when it exits, we're done

    # Export
    if config.output_format == "json":
        output_file = config.output_file
        if output_file.endswith(".csv"):
            output_file = output_file.rsplit(".", 1)[0] + ".json"
        export_collection_json_file(sorted_records, output_file=output_file)
    else:
        export_collection(sorted_records, output_file=config.output_file, delimiter=config.delimiter)

    # Write back (unless --no-write-back) — only if pipeline ran
    if ran_pipeline and has_fields and not config.no_write_back:
        print("Writing sort data back to Discogs…")
        write_count = write_back_sort_data(sorted_records, api, field_ids)
        if write_count > 0:
            print(f"Updated {write_count} custom field values in Discogs.")
        else:
            print("No changes to write back.")
    elif config.no_write_back:
        print("Skipping write-back (--no-write-back).")

    output_path = config.output_file
    if config.output_format == "json" and output_path.endswith(".csv"):
        output_path = output_path.rsplit(".", 1)[0] + ".json"
    print(f"Done! {len(sorted_records)} records sorted → {output_path}")


if __name__ == "__main__":
    main()
