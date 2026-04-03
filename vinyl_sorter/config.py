"""Configuration management for VinylSorter.

Credentials and settings are resolved from CLI arguments, environment
variables, or config files — never hardcoded.
"""

import os
from dataclasses import dataclass, field
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
        )
