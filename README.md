# VinylSorter

Having been dissatisfied with the widely available tools to organize my vinyl collection, and hoping to learn a little bit about coding in python, I mashed two objectives together and created this script. In all fairness it was also a way for me to learn about vibe coding, so almost all the heavy lifting here was done with AI help. Between my noob-ness and the AI I am sure this code fails to meet almost all efficiency and linting standards. I'll work on that.

## Usage

### CLI Mode (sort and export)

```bash
# Install dependencies
pip install -r requirements.txt

# Run with a Discogs token (exports to CSV by default)
python -m vinyl_sorter --token YOUR_TOKEN

# Or set the token as an environment variable
export DISCOGS_TOKEN=YOUR_TOKEN
python -m vinyl_sorter

# Export as JSON instead of CSV
python -m vinyl_sorter --format json

# See all options
python -m vinyl_sorter --help
```

### API Mode (serve over HTTP)

VinylSorter can run as a REST API, serving your sorted collection as JSON with cover art URLs — designed as the backend for a mobile or web app.

```bash
# Run the pipeline, then start the API server
python -m vinyl_sorter --serve

# Specify a port (default: 8000)
python -m vinyl_sorter --serve --port 3000

# Or run standalone with uvicorn (lazy-loads on first request)
export DISCOGS_TOKEN=YOUR_TOKEN
uvicorn vinyl_sorter.api:app --host 0.0.0.0 --port 8000
```

Once running, visit `http://localhost:8000/docs` for interactive Swagger documentation.

#### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service status, version, and collection load state |
| `GET` | `/collection` | Full sorted collection as JSON (includes cover art URLs) |
| `GET` | `/collection/{discogs_id}` | Single record by Discogs release ID |
| `GET` | `/collection/stats` | Aggregate stats: totals, unique artists, year range |
| `POST` | `/collection/refresh` | Re-run the Discogs pipeline and reload the collection |

Each record in the API response includes `thumb_url` (150px) and `cover_image_url` (full-size) for album art.

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--token` | `$DISCOGS_TOKEN` | Discogs personal access token |
| `--user-agent` | `VinylSorter/2.0` | User-Agent for Discogs API |
| `--folder` | `0` (all) | Discogs collection folder index |
| `--output`, `-o` | `sorted_vinyl_collection.csv` | Output file path |
| `--format` | `csv` | Output format: `csv` or `json` |
| `--delimiter` | `,` | Output field delimiter (CSV only) |
| `--serve` | off | Start the API server after sorting |
| `--port` | `8000` | API server port (used with `--serve`) |
| `--log-file` | `vinyl_sorter.log` | Log file path |
| `--log-level` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `--alias-file` | None | JSON file for artist sort-name overrides |
| `--force-reparse` | off | Ignore persisted data and recompute everything |
| `--no-write-back` | off | Don't write computed data back to Discogs |
| `--field-sort-artist` | `Sort Artist` | Discogs custom field name for sort artist |
| `--field-sort-year` | `Sort Year` | Discogs custom field name for sort year |
| `--field-sort-month` | `Sort Month` | Discogs custom field name for sort month |
| `--field-is-compilation` | `Is Compilation` | Discogs custom field name for compilation flag |

### First-Time Setup: Discogs Custom Fields

VinylSorter can save computed sort data back to your Discogs account so that subsequent runs are dramatically faster (seconds instead of minutes). This is optional but highly recommended.

**One-time setup (takes 30 seconds):**

1. Go to your [Discogs Collection Settings](https://www.discogs.com/settings/collection)
2. Under **Collection Notes**, add four new custom fields:
   - **Sort Artist** — type: Textarea
   - **Sort Year** — type: Textarea
   - **Sort Month** — type: Textarea
   - **Is Compilation** — type: Textarea
3. Save your settings

The field names must match exactly (case-insensitive). VinylSorter auto-detects them by name when it starts up and will tell you what it found:

```
Custom fields found: sort_artist→4, sort_year→5, sort_month→6
```

If any fields are missing or misnamed, VinylSorter will warn you and continue without persistence for those fields. Use `--field-sort-artist`, `--field-sort-year`, or `--field-sort-month` to override the expected field names if yours differ.

**What happens on each run:**

| Run | Behavior | Time (300 records) |
|-----|----------|--------------------|
| First run | Computes everything, writes sort data back to Discogs | ~24 min |
| Subsequent runs | Reads persisted data, skips API lookups | ~6 sec |
| New records added | Only new records computed, rest from cache | ~36 sec per 5 new |
| `--force-reparse` | Recomputes everything from scratch | ~24 min |

You can also edit persisted values directly in the Discogs UI — your manual edits will be preserved unless you run with `--force-reparse`.

### Artist Aliases

Create a JSON file to override how artists are sorted:

```json
{
    "The Jerry Garcia Band": "Garcia",
    "Paul McCartney": "Beatles"
}
```

Then: `python -m vinyl_sorter --alias-file aliases.json`

## Algorithm

I think vinyl should be physically sorted by artist, and within artist by date. But that is much easier said than done. Here is a pseudo-code-ish outline of what I think that means practically:

- Sort by artist:
  - If user has defined an alias for this artist → use the alias
  - If record is a compilation Then:
    - sort_artist = "Compilation" and goes after all the single artist records
  - Else (treat record as a single artist release):
    - If artist is an individual Then:
      - If artist has first and last name Then:
        - sort_artist = artist last name
      - Else:
        - sort_artist = artist name
    - Else (treat record as a group):
      - If artist name has a leading unimportant word (such as "The," "A," or "An") Then:
        - sort_artist = artist name stripped of first word
      - Else:
        - sort_artist = artist name
- Sort by date:
  - If record is a studio recording (i.e. not a live or concert recording) Then:
    - If record is a re-release or re-mastered release Then:
      - sort_date = original record release date
    - Else:
      - sort_date = record release date
  - Else:
    - sort_date = recording event date (i.e. the concert date, which might be hard to figure out but most likely appears in the record title or liner notes)

## Project Structure

```
vinyl_sorter/           # Main Python package
  __init__.py           # Package metadata
  __main__.py           # Entry point (python -m vinyl_sorter)
  api.py                # FastAPI REST service
  cli.py                # Command-line argument parsing
  config.py             # Configuration from args/env vars
  constants.py          # Enums and constants
  discogs_api.py        # Discogs API — single session, rate-limited
  models.py             # VinylRecord data model (includes cover art URLs)
  loader.py             # Load collection from Discogs
  parser.py             # Parse sort_artist and sort_year
  sorter.py             # Sort the collection
  exporter.py           # Export to CSV or JSON
  persistence.py        # Write sort data back to Discogs custom fields
docs/                   # Design documents and research
archive/                # Old exploration scripts (preserved for reference)
```

## Good Citizenship

This code logs into Discogs using their APIs and does its best to play nicely. It has access delays and retry logic. It should stay that way.

## Controversial Philosophy Disclaimer

Let's all agree that sorting vinyl by genre is a fool's errand. Do The Cocteau Twins belong in the same genre bucket as Kraftwerk, Big Country, or Philip Glass? There is no winning argument, so let's just skip the whole idea. Or we can agree to disagree. Feel free to write your own code.
