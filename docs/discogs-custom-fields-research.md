# Discogs Custom Fields — Research for Issue #5

## How Custom Fields Work

Discogs allows users to define **custom note fields** on their collection items. These are configured per-user at:
- **UI:** Settings → Collection → Collection Notes ([link](https://www.discogs.com/settings/collection))
- **API:** `GET /users/{username}/collection/fields`

Each field has:
- `field_id` — integer identifier (auto-assigned by Discogs)
- `name` — user-defined label
- `type` — `textarea` or `dropdown`
- `position` — display order
- `public` — whether visible to other users

Default fields include a "Notes" field (field_id typically 3) and a "Media Condition"/"Sleeve Condition" dropdown.

Users can add custom fields beyond the defaults. **There's no documented limit** on count, but forum consensus suggests keeping it reasonable (<10 fields).

## API Endpoints

### Read Custom Fields Definition
```
GET /users/{username}/collection/fields
```
Returns the list of all defined custom fields. Requires authentication as the collection owner.

### Read Field Values on Collection Items
When fetching collection releases:
```
GET /users/{username}/collection/folders/{folder_id}/releases/{release_id}
```
The response includes a `notes` array on each instance:
```json
{
  "notes": [
    {"field_id": 3, "value": "Near Mint condition"},
    {"field_id": 4, "value": "Garcia"},
    {"field_id": 5, "value": "1972"},
    {"field_id": 6, "value": "3"}
  ]
}
```

**Important:** The `notes` section is only returned when authenticated as the collection owner. The general collection folder listing (`collection_folders[0].releases`) also carries these notes per instance.

### Write Field Values
```
POST /users/{username}/collection/folders/{folder_id}/releases/{release_id}/instances/{instance_id}/fields/{field_id}
```
Body: `{"value": "new value"}`

- Requires authentication as the collection owner
- Each instance has an `instance_id` (different from `release_id`)
- You must know the `instance_id`, `folder_id`, and `field_id`
- Setting a value to empty string (`""`) or a space (`" "`) is the only way to "clear" a field — `null` doesn't work
- **Rate limit:** Same as all Discogs API calls — 60 requests/minute for authenticated users

## Python Client Library (`python3-discogs-client`)

Based on the [GitHub discussion #166](https://github.com/joalla/discogs_client/discussions/166), the library has **limited support** for custom fields:

- **Reading:** `CollectionItemInstance` objects have a `notes` property that returns the custom fields when the data is fetched. However, this may require accessing `.data` directly rather than a first-class property.
- **Writing:** There is **no built-in method** for writing custom fields. We'll need to make direct HTTP requests through the client's internal `_request` method or use `requests` directly with the auth token.

### Reading Notes (current library)
```python
for item in user.collection_folders[0].releases:
    instance_data = item.data  # or item.fetch('notes')
    notes = instance_data.get('notes', [])
    for note in notes:
        print(f"Field {note['field_id']}: {note['value']}")
```

### Writing Notes (direct API call needed)
```python
# Using the client's internal session
url = f"/users/{username}/collection/folders/{folder_id}/releases/{release_id}/instances/{instance_id}/fields/{field_id}"
client._post(url, data={"value": "Garcia"})
```

Or fall back to raw requests with the token.

## Proposed Implementation Plan

### Phase 1: Setup (one-time user action)
Quinn creates 3 custom fields in Discogs collection settings:
- **Sort Artist** (textarea)
- **Sort Year** (textarea)
- **Sort Month** (textarea)

Then we store the field_ids in config or auto-detect them by name.

### Phase 2: Read on Load
Modify `loader.py` to capture:
- `instance_id` (needed for write-back)
- `folder_id` (needed for write-back)
- Custom field values from the `notes` array

New fields on `VinylRecord`:
- `instance_id: int`
- `folder_id: int`
- `persisted_sort_artist: Optional[str]`
- `persisted_sort_year: Optional[int]`
- `persisted_sort_month: Optional[int]`

### Phase 3: Skip Computed Fields
In `parser.py`, if persisted values exist → use them, skip API lookups:
```python
if record.persisted_sort_artist:
    record.sort_artist = record.persisted_sort_artist
else:
    record.sort_artist = record.compute_sort_artist(api)
```

### Phase 4: Write Back After Parse
New method in `discogs_api.py`:
```python
def write_custom_field(self, username, folder_id, release_id, instance_id, field_id, value):
    """Write a value to a custom field on a collection instance."""
```

After parsing, write computed values back for any record that:
- Had no persisted value, OR
- Was forced via `--force-reparse`

### Phase 5: CLI Flags
- `--force-reparse` — ignore persisted values, recompute everything, write back
- `--no-write-back` — compute but don't save to Discogs (dry run)

## Performance Estimate

**Current (no persistence):**
| Step | API calls per record | Total for 300 records |
|------|--------------------|-----------------------|
| Load collection | 0 (paginated bulk) | ~6 pages |
| Lookup artist type | 1 | ~200 (deduplicated) |
| Lookup master fields | 1 | 300 |
| Lookup live year | 0.1 (only live) | ~30 |
| **Total** | | **~530 calls ≈ 9 min** |

**With persistence (subsequent runs, no new records):**
| Step | API calls per record | Total for 300 records |
|------|--------------------|-----------------------|
| Load collection + read fields | 0 (included in load) | ~6 pages |
| Skip all lookups | 0 | 0 |
| **Total** | | **~6 calls ≈ 6 sec** |

**With persistence (5 new records):**
| Step | API calls |
|------|-----------|
| Load collection | ~6 pages |
| Lookup new records | ~15 |
| Write back new records | ~15 (3 fields × 5 records) |
| **Total** | **~36 calls ≈ 36 sec** |

**First run with write-back (one-time cost):**
| Step | API calls |
|------|-----------|
| Normal full run | ~530 |
| Write back all records | ~900 (3 fields × 300 records) |
| **Total** | **~1430 calls ≈ 24 min** |

## Gotchas & Limitations

1. **Instance ID required for writes** — Each physical copy in your collection has an `instance_id`. We must capture this during load. The current loader doesn't track it.

2. **No bulk write API** — Each field on each instance is a separate POST. For 300 records × 3 fields = 900 write calls on first run. At 60/min = 15 minutes of writes alone.

3. **Field values are strings** — Even year/month need to be stored as strings and parsed back.

4. **User manual edits win** — If Quinn edits a value in the Discogs UI, we should detect that it differs from what we'd compute and preserve the manual edit. This needs a `--force-reparse` to override.

5. **Notes only visible to authenticated owner** — Won't affect other users viewing Quinn's collection.

6. **Dropdown vs textarea** — We should use `textarea` type for all three fields, since dropdown requires predefined values.

7. **Rate limiting on writes** — The first run with write-back will be slow. Consider a `--write-back` flag that's opt-in rather than automatic, to avoid surprise slow runs.
