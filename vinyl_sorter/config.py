"""Configuration management for VinylSorter.

Credentials and settings are resolved from CLI arguments, environment
variables, or config files — never hardcoded.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Application configuration resolved from args and environment."""

    # Discogs credentials
    discogs_token: str = ""
    discogs_user_agent: str = ""

    # Collection options
    folder_index: int = 0  # 0 = all items in Discogs

    # Output options
    output_file: str = "sorted_vinyl_collection.csv"
    delimiter: str = ","

    # Logging
    log_file: str = "vinyl_sorter.log"
    log_level: str = "INFO"

    # Artist alias file (JSON mapping artist name → sort alias)
    alias_file: Optional[str] = None

    # Output format
    output_format: str = "csv"

    # API server
    serve: bool = False
    port: int = 8000

    # Persistence options
    force_reparse: bool = False
    no_write_back: bool = False
    field_sort_artist: str = "Sort Artist"
    field_sort_year: str = "Sort Year"
    field_sort_month: str = "Sort Month"
    field_is_compilation: str = "Is Compilation"

    # Local cache options
    refresh: bool = False
    cache_file: str = ".vinyl_sorter_cache.json"
    no_cache: bool = False

    @classmethod
    def from_args(cls, args) -> "Config":
        """Build config from parsed CLI arguments, falling back to env vars."""
        return cls(
            discogs_token=(
                args.token
                or os.environ.get("DISCOGS_TOKEN", "")
            ),
            discogs_user_agent=(
                args.user_agent
                or os.environ.get("DISCOGS_USER_AGENT", "VinylSorter/2.0")
            ),
            folder_index=args.folder,
            output_file=args.output,
            delimiter=args.delimiter,
            log_file=args.log_file,
            log_level=args.log_level.upper(),
            alias_file=args.alias_file,
            output_format=getattr(args, "output_format", "csv"),
            serve=getattr(args, "serve", False),
            port=getattr(args, "port", 8000),
            force_reparse=args.force_reparse,
            no_write_back=args.no_write_back,
            field_sort_artist=args.field_sort_artist,
            field_sort_year=args.field_sort_year,
            field_sort_month=args.field_sort_month,
            field_is_compilation=args.field_is_compilation,
            refresh=getattr(args, "refresh", False),
            cache_file=getattr(args, "cache_file", ".vinyl_sorter_cache.json"),
            no_cache=getattr(args, "no_cache", False),
        )
