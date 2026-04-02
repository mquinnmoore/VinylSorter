# VinylSorter

Having been dissatisfied with the widely available tools to organize my vinyl collection, and hoping to learn a little bit about coding in python, I mashed two objectives together and created this script. In all fairness it was also a way for me to learn about vibe coding, so almost all the heavy lifting here was done with AI help. Between my noob-ness and the AI I am sure this code fails to meet almost all efficiency and linting standards. I'll work on that.

## Algorithm

I think vinyl should be psychically sorted by artist, and within artist by date. But that is much easier said than done. Here is a pseudo-code-ish outline of what I think that means practically:


- Sort by artist:
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
      
## Shortcomings

The above describes how this code currently works. However, I realize there are real shortcomings to this approach as it stands and which I will seek to address in future updates. Namely:
- A user might wish to override the sort_artist logic and so there needs to be an alias definition capability. For example:
  - Artist = "The Jerry Garcia Band" -> sort_artist = "Garcia" (which any reasonable person would agree to)
  - Artist = "Paul McCartney" -> sort_artist = "Beatles" (which is heretical misunderstanding of the whole idea here, but even some record stores behave this way, so who am I to judge?)
- This version lacks using passed parameters at run time, which should include (at least):
  - Discogs Oauth credentials
  - Output file name
  - Output file field delimiter
  - Logging file name
  - Logging debug level
  - Artist alias file name
  - Which Discogs collection folder to include
  - Help

## Good Citizenship

This code logs into Disccogs using their APIs and does its best to play nicely. It has access delays and retry logic. It should stay that way.

## Controversial Philosophy Disclaimer

Let's all agree that sorting vinyl by genre is a fool's errand. Do The Cocteau Twins belong in the same genre bucket as Kraftwerk, Big Country, or Philip Glass? There is no winning argument, so let's just skip the whole idea. Or we can agree to disagree. Feel free to write your own code.
