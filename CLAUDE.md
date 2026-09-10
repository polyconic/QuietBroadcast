# QuietBroadcast

One record every six hours, drawn from Greg's Last.fm library. Static HTML, no
build step, no dependencies, no tracking. `README.md` is the public face — keep it
short. This file is the working document.

Not deployed yet. No `CNAME`, no GitHub Pages, no domain.

## The mechanic

Slots are six hours long, counted from `epoch` in `data/schedule.json`:

```
block = floor((now - epoch) / 6h)
record = records[ slots[block] ]
```

Station time is UTC, like delilahsvault — everyone gets the same record at the same
moment, and nothing is stored in the browser.

## The one rule that matters

**`data/schedule.json` is written down, not computed.** `records` is **append-only**
and `slots` holds indexes into it. That is what lets the library grow without
disturbing anything that has already aired.

An earlier version recomputed the past from a clock-seeded shuffle over the pool.
It was tidier and completely wrong: changing the pool size reshuffled every past
slot, so the library could never grow. Don't reintroduce it.

`tools/schedule.py` freezes every slot up to the current block and rebuilds only
what comes after. Records that have never aired get priority; when that queue runs
dry the whole live pool reshuffles, so everything airs once before anything repeats.

**Never reorder or delete entries in `records`.** Slots are positional indexes into
it. Dropping a record from the filters is fine — it just stops being scheduled —
but removing it from the array corrupts every past slot.

## Rebuilding the pool

```bash
python3 tools/pull.py albums
python3 tools/pull.py enrich --min 2
python3 tools/pull.py artists
python3 tools/schedule.py --min-plays-per-track 1 --min-tracks 3 --max-listeners 100000 --genre-fame-pct 0
```

Safe to run any time. New records join the future; aired slots never move.

The API key lives at `~/.lastfm-key` (mode 600) and is read only by `tools/pull.py`
on Greg's machine. **It must never enter the repo or any client-side JS** — the site
makes zero API calls at runtime and should stay that way.

## The filters, and why each exists

| Filter | Default | Why |
|---|---|---|
| `--min-plays-per-track` | 1.0 | A Last.fm "play" is one **track** scrobble, so raw play count is biased against short EPs. Dividing by tracklist length gives complete listens. |
| `--min-tracks` | 3 | A record, not a single. Without it 419 of 1,105 entries were 1-track singles. |
| `--max-listeners` | 100000 | Fame ceiling. Discovery means not airing what everyone has heard. |
| `--genre-fame-pct` | 0 | Trims each genre's canon. Only useful on a multi-genre pool; redundant now the pool is electronic-only. |
| `--max-minutes` | 120 | Above this it is a box set, not a record. |
| `--allow-artless` | off | By default a record with no sleeve is dropped — the front page is mostly the sleeve. |
| `--all-genres` | off | Turns off the electronic-adjacent gate. |

`ELECTRONIC_TAGS` is the gate. Trip-hop and sample-based instrumental beats are in
(same machines); vocal rap and guitar music are out unless also tagged electronic.
Two judgement calls worth knowing: disco and dub are in, because nu-disco and dub
techno are entangled with the rest; and Gorillaz and Fishmans get through on their
electronic tags, which is "adjacent" behaving as asked.

`EXCLUDE_ARTISTS` keeps records off the station entirely: Greg's own (`gregor egan`)
and `goose`, which slipped the electronic gate on a stray tag. Exact artist match.

**Artless records are dropped.** `schedule.py` imports `url_map()` from `art.py` to see
what the local cache has a sleeve URL for, and also reads `data/art_failed.json` — the
handful whose URLs 404 on every size — so both are gone before scheduling. Run
`tools/art.py` after `tools/schedule.py`; if it records new failures, run the scheduler
once more to drop them. `art.py` also prunes sleeves nothing references any more.

**`Various Artists` is not an artist.** Compilations still air, but `NOT_AN_ARTIST` in
`log.html` keeps the label out of the artist count, the "keeps coming back" list and
the network graph.

## Last.fm quirks — do not rediscover these

- A **listener** is a distinct user; a **play** is a scrobble. The fame ceiling uses
  `listeners`, the taste filter uses Greg's own `plays`. Global `playcount` is unused.
- Loved tracks are useless as a signal — he has 27.
- `duration` comes back as an int sometimes and a string others. `tags` is an empty
  **string**, not an empty object, when absent. Shape-check everything; `listify()`
  in `pull.py` exists for this.
- 434 albums have no tracklist at all and can't be scored.
- Album tags are patchy. `tools/pull.py artists` fetches artist-level tags as a
  fallback and filled 182 of 183 gaps. Only tags with 15+ votes are accepted.
- Durations under 60s per track are wrong, not short — `clean()` blanks the number
  and keeps the record rather than dropping a good album over bad metadata.

## Pages

| File | What it is |
|---|---|
| `index.html` | The slot. Sleeve, one record, its tracklist, where to get it. |
| `log.html` | Everything aired, in prose; the artist network; a journal of recent days. |
| `tools/art.py` | Sleeve art from the local cache into `art/`. |

The network graph is a hand-rolled force simulation on canvas — no library. Edges join
artists sharing **two or more** tags; one shared tag connects everything to everything.
It pre-runs 600 steps so it opens settled. Three things it needs to stay readable, all
of which it got wrong first time round:

- **Repulsion must have a cutoff** (`spacing*2.2`). Applied to every pair it sums
  outward, inflating the layout until the walls stop it and every node ends up lined
  along the edges.
- **Hard separation after integration**, so circles never overlap, plus a soft inward
  nudge near the walls rather than only a clamp — a clamp alone makes nodes slide along
  the edge and queue up.
- **Labels are placed biggest-first and skipped on collision**, trying right, left,
  above, below. Without that, names print straight through one another. Hover or
  selection forces a label through with a background plate.

`?preview=N` renders slot N on either page. Undocumented dev affordance, not a feature.

## Voice and look

The pages are meant to read like the back of a sleeve, not an instrument panel.
Greg asked for "organic, less dashboard" after a first pass that was all
monospace caps, pills, bordered buttons, stat tiles and bar charts. So:

- **System serif** for nearly everything (`--serif`: Iowan Old Style / Palatino /
  Georgia — nothing is fetched). Sans only for artist names and durations.
- **Prose where there were labels.** "Four tracks, twenty-two minutes — techno, dub
  techno." Small numbers are spelled out (`words()`). The countdown is a sentence
  that updates every 30s, not a ticking clock.
- **The four slots are named**, not numbered: *in the small hours* (00:00), *morning*
  (06:00), *afternoon* (12:00), *evening* (18:00). Station time is UTC.
- The log's stats are a paragraph, tags are a weighted type cloud, recent slots are
  a journal grouped by day. No tiles, no bars.
- Tracklist uses dotted leaders and CSS counters — no hairlines, no mono numbers.

**Colour:** the chrome is greyscale; `--accent` `#e02b1d` (the vault's red) is only the
on-air lamp and "on air now". Everything else colourful on the page is **sampled from
the sleeve currently on air** — `tint()` averages the image (weighted toward saturated
pixels, pushed away from grey) and sets `--glow`, which feeds two slow-drifting blurred
blobs and the sleeve's shadow. The art is served from this origin, so the canvas read
is untainted. A near-grey sleeve still yields something; a missing sleeve leaves the
default grey.

Film grain is an inline SVG turbulence, ~4.5% opacity. All motion respects
`prefers-reduced-motion`.

**Sleeves** live in `art/` via `tools/art.py` — it reads the local API cache and makes
no API calls, downloads 12-wide, and converts with ImageMagick to **webp q85, capped at
800px** (the sleeve renders ~360px, so 800 covers retina; `>` never upscales).

Two things about Last.fm images worth keeping: `mega` and `extralarge` are the *same*
300px file, but **stripping the size segment from the URL** (`/i/u/300x300/x.png` →
`/i/u/x.png`) returns the original, usually 600–1400px. And some sizes 404 per release,
so `candidates()` keeps the whole ladder as fallbacks. Records with no usable sleeve are
dropped from the pool entirely.

## Theme

Shared `localStorage` key `theme`, `light`/`dark`, dark by default, same as the other
sites. Light is warm paper (`#efece6`), not white. Reads and writes are wrapped in
try/catch — `localStorage` throws on `file:` and `data:` origins.

## Local preview

```bash
python3 -m http.server 8733 --directory .
```
