"""Bin-break insertion for the sorted collection.

Implements middle-balanced bin distribution: when the user passes
``--bins N`` to the CLI, the sorted record list is partitioned into
``N`` bins with sizes that differ by at most one, and a synthetic
"``Bin Break``" separator record is inserted between adjacent bins.

The extras (when ``n % b != 0``) are distributed starting from the
middle bin and alternating outward (``0, +1, -1, +2, -2, ...``) so
the cover flow visual stays balanced left-to-right.
"""

from __future__ import annotations

import sys
from typing import List, Optional

from .models import VinylRecord


class BinValidationError(ValueError):
    """Raised when ``--bins`` is given a value that's out of range.

    ``__main__.main`` catches this, prints ``Error: <message>`` to
    stderr, and exits with code 1.
    """


def compute_bin_sizes(n: int, b: int) -> List[int]:
    """Return the bin sizes for ``n`` records distributed across ``b`` bins.

    Sizes differ by at most one. The remainder is distributed starting
    from the left-middle bin and alternating outward, so the extras
    cluster around the geometric center of the layout.

    For odd ``b``, the middle bin is unambiguous (``(b - 1) // 2 ==
    b // 2``). For even ``b``, picking the left-middle keeps the
    extras balanced around the actual two-center (e.g. ``b=4`` →
    indices 1 and 2) rather than skewed to the right.

    Args:
        n: Total number of real records to distribute.
        b: Number of bins (must be >= 1).

    Returns:
        A list of length ``b`` whose entries sum to ``n``. When ``n``
        divides ``b`` evenly, every bin gets ``n // b``.

    Examples:
        >>> compute_bin_sizes(91, 3)
        [30, 31, 30]
        >>> compute_bin_sizes(90, 4)
        [22, 23, 23, 22]
        >>> compute_bin_sizes(60, 3)
        [20, 20, 20]
    """
    base = n // b
    rem = n % b
    sizes = [base] * b
    if rem == 0:
        return sizes

    middle = (b - 1) // 2
    # offsets: 0, +1, -1, +2, -2, ... so extras cluster around the middle
    offsets = [0]
    for k in range(1, b):
        offsets.append(k)
        offsets.append(-k)

    for off in offsets[:rem]:
        idx = middle + off
        if 0 <= idx < b:
            sizes[idx] += 1

    return sizes


def validate_bins(bins: Optional[int], record_count: int) -> None:
    """Validate the ``--bins`` value against the current record count.

    The rules match the CLI help text: ``bins`` must be at least 2
    and at most ``record_count``. A ``bins`` value of ``None``
    (i.e. the flag was omitted) is always valid.

    Args:
        bins: The user-supplied ``--bins`` value, or ``None``.
        record_count: Number of records that will be binned.

    Raises:
        BinValidationError: If ``bins`` is out of range. The exception
            message omits the ``Error: `` prefix — callers add that
            so the message can be routed through stderr consistently.
    """
    if bins is None:
        return
    if bins < 2:
        raise BinValidationError(f"--bins must be at least 2 (got {bins}).")
    if bins > record_count:
        raise BinValidationError(
            f"--bins ({bins}) cannot exceed number of records ({record_count})."
        )


def _make_bin_break() -> VinylRecord:
    """Construct a synthetic ``Bin Break`` separator record.

    The values are intentionally sentinel-shaped so that:

    * the CSV row renders with a blank ``Sort #``, ``Artist``,
      ``Sort Year``, etc. (handled by the exporter), and
    * the write-back path can trivially filter these out (they have
      ``discogs_id == -1`` and ``is_bin_break is True``).
    """
    return VinylRecord(
        is_bin_break=True,
        release_title="Bin Break",
        release_artist="",
        sort_artist="",
        release_year=-1,
        sort_year=-1,
        sort_month=0,
        sort_sequence=-1,
        discogs_id=-1,
        instance_id=-1,
        cover_image_url="",
        thumb_url="",
    )


def insert_bin_breaks(
    records: List[VinylRecord],
    b: int,
) -> List[VinylRecord]:
    """Return a new list with ``b - 1`` bin-break records inserted.

    The records list is partitioned into ``b`` bins of sizes
    :func:`compute_bin_sizes` (middle-balanced). Between each pair
    of adjacent bins, exactly one ``Bin Break`` separator record is
    inserted.

    Args:
        records: Sorted list of real ``VinylRecord`` objects.
        b: Number of bins (must be >= 2 and <= ``len(records)``).
            Callers are expected to validate this before invocation.

    Returns:
        A new list of length ``len(records) + (b - 1)``. The input
        list is not mutated. Bin break records carry
        ``is_bin_break=True`` and a sentinel-shaped payload — see
        :func:`_make_bin_break`.
    """
    sizes = compute_bin_sizes(len(records), b)

    result: List[VinylRecord] = []
    cursor = 0
    for bin_idx, size in enumerate(sizes):
        # Append this bin's slice of real records.
        result.extend(records[cursor:cursor + size])
        cursor += size
        # Append a separator after every bin except the last.
        if bin_idx < b - 1:
            result.append(_make_bin_break())

    return result
