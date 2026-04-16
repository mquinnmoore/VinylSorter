"""FastAPI application for serving the vinyl collection as a REST API.

This module provides a clean API layer that consumes the existing
VinylSorter pipeline without modifying it. The collection is loaded
once (on startup or first request) and cached in memory. A refresh
endpoint re-runs the full pipeline.

Can be used in two modes:
1. CLI mode: ``python -m vinyl_sorter --serve`` — pipeline runs first,
   sorted records are passed directly to ``create_app()``.
2. Standalone mode: ``uvicorn vinyl_sorter.api:app`` — reads config from
   environment variables and runs the pipeline on first request.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .exporter import record_to_dict
from .models import VinylRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------

class RecordResponse(BaseModel):
    """API response schema for a single vinyl record."""

    discogs_id: int = Field(..., description="Discogs release ID")
    sort_sequence: int = Field(..., description="Position in the sorted collection")
    release_artist: str = Field(..., description="Artist name from Discogs")
    sort_artist: str = Field(..., description="Computed artist name used for sorting")
    release_title: str = Field(..., description="Album title from Discogs")
    release_year: int = Field(..., description="Release year from Discogs")
    sort_year: int = Field(..., description="Computed year used for sorting (may differ for re-releases)")
    sort_month: int = Field(..., description="Computed month used for sorting (0 = unknown)")
    is_compilation: bool = Field(..., description="Whether this is a compilation/various-artists release")
    is_live: bool = Field(..., description="Whether this is a live recording")
    cover_image_url: str = Field("", description="Full-size cover art URL")
    thumb_url: str = Field("", description="150px thumbnail URL")

    model_config = {"json_schema_extra": {"example": {
        "discogs_id": 1234567,
        "sort_sequence": 42,
        "release_artist": "The Beatles",
        "sort_artist": "Beatles",
        "release_title": "Abbey Road",
        "release_year": 1969,
        "sort_year": 1969,
        "sort_month": 9,
        "is_compilation": False,
        "is_live": False,
        "cover_image_url": "https://img.discogs.com/...",
        "thumb_url": "https://img.discogs.com/.../150.jpg",
    }}}


class CollectionStatsResponse(BaseModel):
    """API response schema for collection statistics."""

    total_records: int = Field(..., description="Total number of records in the collection")
    total_artists: int = Field(..., description="Number of unique sort artists")
    total_compilations: int = Field(..., description="Number of compilation records")
    year_range: Optional[Dict[str, int]] = Field(
        None, description="Earliest and latest sort year (null if collection is empty)"
    )
    loaded_at: str = Field(..., description="ISO timestamp of when the collection was last loaded")


class HealthResponse(BaseModel):
    """API response schema for health check."""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="VinylSorter version")
    collection_loaded: bool = Field(..., description="Whether the collection has been loaded")
    record_count: int = Field(..., description="Number of records loaded (0 if not yet loaded)")


class RefreshResponse(BaseModel):
    """API response for a collection refresh."""

    status: str
    record_count: int
    message: str


class CacheStatusResponse(BaseModel):
    """API response for cache status."""

    has_cache: bool = Field(..., description="Whether a local cache file exists")
    cached_at: Optional[str] = Field(None, description="ISO timestamp of when the cache was written")
    cached_ago: Optional[str] = Field(None, description="Human-friendly time since cache was written")
    record_count: Optional[int] = Field(None, description="Number of records in the cache")
    cache_file: Optional[str] = Field(None, description="Path to the cache file")
    discogs_count: Optional[int] = Field(None, description="Current Discogs collection count")
    is_current: Optional[bool] = Field(None, description="Whether cache count matches Discogs count")


# ---------------------------------------------------------------------------
# Collection state
# ---------------------------------------------------------------------------

class _CollectionState:
    """Thread-safe container for the in-memory collection cache."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: List[VinylRecord] = []
        self._loaded_at: Optional[datetime] = None

    @property
    def is_loaded(self) -> bool:
        return self._loaded_at is not None

    @property
    def loaded_at(self) -> Optional[datetime]:
        return self._loaded_at

    @property
    def records(self) -> List[VinylRecord]:
        return self._records

    def set_records(self, records: List[VinylRecord]) -> None:
        with self._lock:
            self._records = list(records)
            self._loaded_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Pipeline runner (for standalone mode)
# ---------------------------------------------------------------------------

def _run_pipeline() -> List[VinylRecord]:
    """Run the full VinylSorter pipeline using environment variable config.

    This is used when the API is started standalone (not via CLI --serve).

    Returns:
        Sorted list of VinylRecord objects.

    Raises:
        RuntimeError: If DISCOGS_TOKEN is not set or Discogs is unreachable.
    """
    from .config import Config
    from .discogs_api import DiscogsAPI
    from .loader import load_collection
    from .parser import load_aliases, parse_collection
    from .sorter import sort_collection

    token = os.environ.get("DISCOGS_TOKEN", "")
    if not token:
        raise RuntimeError(
            "DISCOGS_TOKEN environment variable is not set. "
            "The API requires a valid Discogs personal access token."
        )

    user_agent = os.environ.get("DISCOGS_USER_AGENT", "VinylSorter/2.0")

    try:
        api = DiscogsAPI(user_agent=user_agent, token=token)
    except Exception as exc:
        raise RuntimeError(f"Failed to connect to Discogs: {exc}") from exc

    # Resolve custom field IDs
    field_ids = api.resolve_field_ids({
        "sort_artist": "Sort Artist",
        "sort_year": "Sort Year",
        "sort_month": "Sort Month",
        "is_compilation": "Is Compilation",
    })
    has_fields = any(v is not None for v in field_ids.values())

    records = load_collection(
        api,
        folder_index=0,
        field_ids=field_ids if has_fields else None,
    )

    aliases = load_aliases(os.environ.get("VINYL_SORTER_ALIAS_FILE"))
    parse_collection(records, api, aliases=aliases)

    return sort_collection(records)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(
    records: Optional[List[VinylRecord]] = None,
    config: Optional[Any] = None,
) -> FastAPI:
    """Create the FastAPI application.

    Args:
        records: Pre-sorted records from the CLI pipeline. If None,
            the API will run the pipeline on first request using
            environment variables for configuration.
        config: Optional Config object for cache file location.

    Returns:
        Configured FastAPI application instance.
    """
    from . import __version__
    from .cache import get_cache_metadata, save_cache, DEFAULT_CACHE_FILE

    cache_file = DEFAULT_CACHE_FILE
    no_cache = False
    if config is not None:
        cache_file = getattr(config, "cache_file", DEFAULT_CACHE_FILE)
        no_cache = getattr(config, "no_cache", False)

    app = FastAPI(
        title="VinylSorter API",
        description="REST API for a sorted vinyl record collection powered by Discogs.",
        version=__version__,
    )

    state = _CollectionState()
    if records is not None:
        state.set_records(records)

    def _ensure_loaded() -> List[VinylRecord]:
        """Ensure the collection is loaded, running the pipeline if needed."""
        if not state.is_loaded:
            try:
                sorted_records = _run_pipeline()
                state.set_records(sorted_records)
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=503,
                    detail=str(exc),
                ) from exc
        return state.records

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health_check():
        """Health check endpoint."""
        return HealthResponse(
            status="ok",
            version=__version__,
            collection_loaded=state.is_loaded,
            record_count=len(state.records) if state.is_loaded else 0,
        )

    @app.get(
        "/collection/stats",
        response_model=CollectionStatsResponse,
        tags=["collection"],
    )
    def collection_stats():
        """Return aggregate statistics about the collection."""
        records = _ensure_loaded()

        if not records:
            return CollectionStatsResponse(
                total_records=0,
                total_artists=0,
                total_compilations=0,
                year_range=None,
                loaded_at=state.loaded_at.isoformat() if state.loaded_at else "",
            )

        artists = {r.sort_artist for r in records if not r.is_compilation}
        compilations = sum(1 for r in records if r.is_compilation)
        valid_years = [r.sort_year for r in records if r.sort_year > 0]

        return CollectionStatsResponse(
            total_records=len(records),
            total_artists=len(artists),
            total_compilations=compilations,
            year_range={
                "earliest": min(valid_years),
                "latest": max(valid_years),
            } if valid_years else None,
            loaded_at=state.loaded_at.isoformat() if state.loaded_at else "",
        )

    @app.get(
        "/collection/{discogs_id}",
        response_model=RecordResponse,
        tags=["collection"],
    )
    def get_record(discogs_id: int):
        """Return a single record by its Discogs release ID."""
        records = _ensure_loaded()

        for record in records:
            if record.discogs_id == discogs_id:
                return RecordResponse(**record_to_dict(record))

        raise HTTPException(
            status_code=404,
            detail=f"Record with discogs_id {discogs_id} not found in collection.",
        )

    @app.get(
        "/collection",
        response_model=List[RecordResponse],
        tags=["collection"],
    )
    def get_collection():
        """Return the full sorted collection."""
        records = _ensure_loaded()
        return [RecordResponse(**record_to_dict(r)) for r in records]

    @app.post(
        "/collection/refresh",
        response_model=RefreshResponse,
        tags=["collection"],
    )
    def refresh_collection():
        """Re-run the full pipeline and refresh the cached collection.

        This is only available when running in standalone mode (the pipeline
        uses environment variables for configuration). In CLI --serve mode
        it will still work but re-runs from environment config.
        """
        try:
            sorted_records = _run_pipeline()
            state.set_records(sorted_records)

            # Update the local cache file
            if not no_cache:
                try:
                    save_cache(sorted_records, cache_file)
                except Exception as exc:
                    logger.warning("Failed to update cache after refresh: %s", exc)

            return RefreshResponse(
                status="ok",
                record_count=len(sorted_records),
                message=f"Collection refreshed: {len(sorted_records)} records loaded.",
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get(
        "/collection/cache-status",
        response_model=CacheStatusResponse,
        tags=["system"],
    )
    def cache_status():
        """Return metadata about the local cache file.

        Includes whether the cache exists, when it was last updated,
        the record count, and whether it matches the current Discogs
        collection count.
        """
        if no_cache:
            return CacheStatusResponse(
                has_cache=False,
            )

        meta = get_cache_metadata(cache_file)
        if meta is None:
            return CacheStatusResponse(
                has_cache=False,
            )

        # Try a lightweight Discogs count check
        discogs_count = None
        is_current = None
        try:
            token = os.environ.get("DISCOGS_TOKEN", "")
            if token:
                from .discogs_api import DiscogsAPI as _API
                user_agent = os.environ.get("DISCOGS_USER_AGENT", "VinylSorter/2.0")
                _api = _API(user_agent=user_agent, token=token)
                discogs_count = _api.collection_count()
                is_current = (discogs_count == meta.record_count)
        except Exception as exc:
            logger.warning("Could not check Discogs count for cache-status: %s", exc)

        return CacheStatusResponse(
            has_cache=True,
            cached_at=meta.cached_at.isoformat(),
            cached_ago=meta.cached_ago,
            record_count=meta.record_count,
            cache_file=meta.cache_file,
            discogs_count=discogs_count,
            is_current=is_current,
        )

    return app


# ---------------------------------------------------------------------------
# Standalone entry point: ``uvicorn vinyl_sorter.api:app``
# ---------------------------------------------------------------------------

app = create_app()
