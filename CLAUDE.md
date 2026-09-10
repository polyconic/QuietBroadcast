# NodeRecord

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
| `--all-genres` | off | Turns off the electronic-adjacent gate. |

`ELECTRONIC_TAGS` is the gate. Trip-hop and sample-based instrumental beats are in
(same machines); vocal rap and guitar music are out unless also tagged electronic.
Two judgement calls worth knowing: disco and dub are in, because nu-disco and dub
techno are entangled with the rest; and Gorillaz and Fishmans get through on their
electronic tags, which is "adjacent" behaving as asked.

`EXCLUDE_ARTISTS` keeps Greg's own records off the station. Exact artist match — his
library only has the one credit spelling, `Gregor Egan`, so that is safe here.

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
| `index.html` | The slot. One record, its tracklist, where to get it, countdown. |
| `log.html` | Everything aired, tag and length stats, and the artist network. |

The network graph is a hand-rolled force simulation on canvas — no library. Edges
join artists sharing **two or more** tags; one shared tag connects everything to
everything. It pre-runs 420 steps before the first paint so it opens settled.

`?preview=N` renders slot N on either page. Undocumented dev affordance, not a feature.

## Theme

Shared `localStorage` key `theme`, `light`/`dark`, dark by default, same as the other
sites. Reads and writes are wrapped in try/catch — `localStorage` throws on `file:`
and `data:` origins and an unguarded access kills the rest of the script.

`--accent` `#e02b1d` is the only colour, same red as the vault.

## Local preview

```bash
python3 -m http.server 8733 --directory .
```
