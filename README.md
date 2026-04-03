# VinylSorter

Having been dissatisfied with the widely available tools to organize my vinyl collection, and hoping to learn a little bit about coding in python, I mashed two objectives together and created this script. In all fairness it was also a way for me to learn about vibe coding, so almost all the heavy lifting here was done with AI help. Between my noob-ness and the AI I am sure this code fails to meet almost all efficiency and linting standards. I'll work on that.

## Usage

```bash
# Install dependencies
pip install -r requirements.txt

# Run with a Discogs token
python -m vinyl_sorter --token YOUR_TOKEN

# Or set the token as an environment variable
export DISCOGS_TOKEN=YOUR_TOKEN
python -m vinyl_sorter

# See all options
python -m vinyl_sorter --help
```

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--token` | `$DISCOGS_TOKEN` | Discogs personal access token |
| `--user-agent` | `VinylSorter/2.0` | User-Agent for Discogs API |
| `--folder` | `0` (all) | Discogs collection folder index |
| `--output`, `-o` | `sorted_vinyl_collection.csv` | Output file path |
| `--delimiter` | `,` | Output field delimiter |
| `--log-file` | `vinyl_sorter.log` | Log file path |
| `--log-level` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `--alias-file` | None | JSON file for artist sort-name overrides |

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
  cli.py                # Command-line argument parsing
  config.py             # Configuration from args/env vars
  constants.py          # Enums and constants
  discogs_api.py        # Discogs API — single session, rate-limited
  models.py             # VinylRecord data model
  loader.py             # Load collection from Discogs
  parser.py             # Parse sort_artist and sort_year
  sorter.py             # Sort the collection
  exporter.py           # Export to CSV
archive/                # Old exploration scripts (preserved for reference)
```

## Good Citizenship

This code logs into Discogs using their APIs and does its best to play nicely. It has access delays and retry logic. It should stay that way.

## Controversial Philosophy Disclaimer

Let's all agree that sorting vinyl by genre is a fool's errand. Do The Cocteau Twins belong in the same genre bucket as Kraftwerk, Big Country, or Philip Glass? There is no winning argument, so let's just skip the whole idea. Or we can agree to disagree. Feel free to write your own code.
