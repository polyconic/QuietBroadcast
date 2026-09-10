#!/usr/bin/env python3
"""Build the broadcast schedule. Past slots are frozen; only the future is rewritten.

  python3 tools/schedule.py                  # extend the schedule from data/albums.json
  python3 tools/schedule.py --horizon 365    # how many days ahead to fill

`records` is APPEND-ONLY and `slots` holds indexes into it, so re-syncing Last.fm
adds to the pool without disturbing a single slot that has already aired.
"""
import argparse, json, os, random, re, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
SCHED = os.path.join(DATA, "schedule.json")
POOL = os.path.join(DATA, "albums.json")
EPOCH = "2026-09-10"

# Your own records stay off the station.
EXCLUDE_ARTISTS = {"gregor egan"}

# Fame is relative to scene: 30k listeners is canonical in techno and nothing in rock.
# So the canon is trimmed per genre, then a hard ceiling catches the outright megahits.
GENRE_FAMILIES = {
    "techno":     ("techno", "minimal techno", "tech house", "acid techno",
                   "hard techno", "industrial techno", "dub techno"),
    "electronic": ("electronic", "idm", "ambient", "house", "deep house", "downtempo",
                   "electronica", "dance", "drum and bass", "jungle", "breakbeat"),
    "hip-hop":    ("hip-hop", "hip hop", "rap", "trap", "jazz rap", "boom bap"),
    "rock":       ("rock", "classic rock", "indie rock", "alternative rock", "hard rock",
                   "punk", "punk rock", "metal", "heavy metal", "grunge", "post-punk",
                   "psychedelic rock", "progressive rock", "folk rock", "garage rock"),
    "jazz/soul":  ("jazz", "soul", "funk", "rnb", "blues", "neo-soul"),
}


# Electronic-adjacent: made with computers and synths. Trip-hop and sample-based
# instrumental beats count; guitar music does not, unless it is also tagged electronic.
ELECTRONIC_TAGS = {
    # techno and house
    "techno", "minimal techno", "hard techno", "acid techno", "industrial techno",
    "dub techno", "detroit techno", "melodic techno", "peak time techno",
    "house", "deep house", "tech house", "acid house", "lo-fi house", "minimal house",
    "progressive house", "microhouse", "minimal", "acid", "electro",
    # the umbrella
    "electronic", "electronica", "idm", "ambient", "dark ambient", "drone",
    "downtempo", "chillout", "chill", "trip-hop", "trip hop", "glitch",
    "experimental electronic", "leftfield", "braindance", "abstract",
    # bass and breaks
    "drum and bass", "dnb", "jungle", "breakbeat", "breaks", "dubstep",
    "uk garage", "garage", "2-step", "bass", "footwork", "juke",
    # synth-led
    "synthpop", "synth-pop", "synthwave", "darkwave", "coldwave", "ebm",
    "industrial", "new wave", "minimal wave", "italo disco", "nu disco", "disco",
    # trance and harder
    "trance", "psytrance", "goa trance", "hardcore", "gabber", "hardstyle",
    "big beat", "trip rock",
    # beat-tape / instrumental hip-hop, same machines as trip-hop
    "instrumental hip-hop", "abstract hip-hop", "wonky", "beats", "lo-fi",
    "lo-fi hip hop", "vaporwave", "chillwave", "future garage", "dub",
}


def is_electronic(tags):
    return bool(ELECTRONIC_TAGS & set(tags))


def family(r):
    t = set(r.get("tags") or [])
    for name, tags in GENRE_FAMILIES.items():
        if t & set(tags):
            return name
    return "other"


def trim_famous(pool, pct, hard):
    """Drop the best-known slice of each genre, then anything famous outright."""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in pool:
        groups[family(r)].append(r)
    keep = []
    for name, rs in groups.items():
        rs.sort(key=lambda r: -(r.get("listeners") or 0))
        keep += rs[int(len(rs) * pct):]
    out = [r for r in keep if (r.get("listeners") or 0) < hard]
    print("  fame trim: top %d%% of each genre and anything over %s listeners"
          % (pct * 100, format(hard, ",")))
    print("  %d of %d records survive" % (len(out), len(pool)))
    return out
HOURS = 6

FIELDS = ("artist", "release", "tags", "tracks", "secs", "url", "plays")


def key(r):
    return r["artist"] + "  " + r["release"]


EDITION = re.compile(r"\s*[\(\[][^)\]]*"
                     r"(remaster|deluxe|edition|version|expanded|anniversary|super|mono|stereo)"
                     r"[^)\]]*[\)\]]", re.I)


def base_title(t):
    return re.sub(r"[^a-z0-9]+", "", EDITION.sub("", t).lower())


def clean(pool, max_minutes):
    """Last.fm durations are patchy and editions duplicate. Fix what is fixable,
    drop what is not a record."""
    out, boxed = [], 0
    for r in pool:
        nt = len(r.get("tracks") or [])
        secs = r.get("secs") or 0
        # under a minute a track means the durations are wrong, not that the
        # record is short - keep the record, drop the bogus number
        if nt and secs and secs / nt < 60:
            r = dict(r, secs=0, tracks=[dict(t, secs=0) for t in r["tracks"]])
            secs = 0
        if secs and secs > max_minutes * 60:
            boxed += 1
            continue
        out.append(r)

    best = {}
    for r in out:
        k = (r["artist"].lower(), base_title(r["release"]))
        if k not in best or r["plays"] > best[k]["plays"]:
            best[k] = r
    deduped = list(best.values())
    print("  cleaned: %d box sets over %d min, %d duplicate editions merged"
          % (boxed, max_minutes, len(out) - len(deduped)))
    return deduped


def now_block(epoch, hours):
    t0 = datetime.fromisoformat(epoch).replace(tzinfo=timezone.utc).timestamp()
    return int((time.time() - t0) // (hours * 3600))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--horizon", type=int, default=180, help="days to fill ahead")
    p.add_argument("--min-plays-per-track", type=float, default=0.0)
    p.add_argument("--min-tracks", type=int, default=3,
                   help="a record, not a single")
    p.add_argument("--max-minutes", type=int, default=120,
                   help="above this it is a box set, not a record")
    p.add_argument("--exclude", action="append", default=[],
                   help="artist to keep off the station (repeatable)")
    p.add_argument("--all-genres", action="store_true",
                   help="keep non-electronic music too")
    p.add_argument("--genre-fame-pct", type=float, default=0.35,
                   help="drop this share of each genre's best-known records")
    p.add_argument("--max-listeners", type=int, default=400000,
                   help="hard ceiling on Last.fm listeners; 0 keeps all")
    a = p.parse_args()

    if not os.path.exists(POOL):
        sys.exit("No data/albums.json - run tools/pull.py first.")
    pool = json.load(open(POOL))

    if a.min_plays_per_track or a.min_tracks > 1:
        keep, untracked, singles = [], 0, 0
        for r in pool:
            nt = len(r.get("tracks") or [])
            if not nt:
                untracked += 1          # no tracklist from Last.fm, can't be scored
                continue
            if nt < a.min_tracks:
                singles += 1
                continue
            if r["plays"] / nt >= a.min_plays_per_track:
                keep.append(r)
        print("  %d of %d albums kept (>=%.1f plays/track, >=%d tracks)"
              % (len(keep), len(pool), a.min_plays_per_track, a.min_tracks))
        print("  dropped: %d with no tracklist, %d shorter than %d tracks"
              % (untracked, singles, a.min_tracks))
        pool = keep

    at_path = os.path.join(DATA, "artist_tags.json")
    artist_tags = json.load(open(at_path)) if os.path.exists(at_path) else {}
    if artist_tags:
        filled = 0
        for r in pool:
            if not r.get("tags") and artist_tags.get(r["artist"]):
                r["tags"] = artist_tags[r["artist"]][:6]
                filled += 1
        print("  filled tags on %d records from artist tags" % filled)

    if not a.all_genres:
        before = len(pool)
        untagged = [r for r in pool if not r.get("tags")]
        pool = [r for r in pool if is_electronic(r.get("tags") or [])]
        print("  electronic-adjacent only: %d of %d kept (%d had no tags at all)"
              % (len(pool), before, len(untagged)))

    banned = EXCLUDE_ARTISTS | {x.lower() for x in a.exclude}
    before = len(pool)
    pool = [r for r in pool if r["artist"].lower() not in banned]
    if len(pool) < before:
        print("  excluded %d records by %s" % (before - len(pool), ", ".join(sorted(banned))))

    if a.genre_fame_pct or a.max_listeners:
        pool = trim_famous(pool, a.genre_fame_pct,
                           a.max_listeners or 10 ** 12)

    pool = clean(pool, a.max_minutes)

    if os.path.exists(SCHED):
        sched = json.load(open(SCHED))
    else:
        sched = {"epoch": EPOCH, "hours": HOURS, "records": [], "slots": []}

    records = sched["records"]
    index = {key(r): i for i, r in enumerate(records)}

    # Append-only: new records join the end, existing ones keep their index.
    added = 0
    for r in pool:
        k = key(r)
        if k not in index:
            index[k] = len(records)
            records.append({f: r.get(f) for f in FIELDS})
            added += 1
    live = set(index[key(r)] for r in pool)

    cur = now_block(sched["epoch"], sched["hours"])
    frozen = sched["slots"][: max(0, cur + 1)]
    if len(frozen) < len(sched["slots"]):
        print("  freezing %d aired slots, rebuilding %d future ones"
              % (len(frozen), len(sched["slots"]) - len(frozen)))

    per_day = 24 // sched["hours"]
    horizon = cur + 1 + a.horizon * per_day

    # Records that have never aired go first; when that runs out the whole live
    # pool reshuffles, so everything airs once before anything repeats.
    ever = set(frozen)
    unaired = [i for i in live if i not in ever]
    rnd = random.Random(20260901 + len(frozen))
    rnd.shuffle(unaired)

    slots = list(frozen)
    queue = list(unaired)
    while len(slots) < horizon:
        if not queue:
            queue = sorted(live)
            rnd.shuffle(queue)
        slots.append(queue.pop())

    sched["records"] = records
    sched["slots"] = slots
    json.dump(sched, open(SCHED, "w"), ensure_ascii=False, separators=(",", ":"))

    aired = len(frozen)
    never = len([i for i in live if i not in ever])
    print("  %d records in the schedule (%d new)" % (len(records), added))
    print("  %d slots aired, %d scheduled ahead (~%d days)"
          % (aired, len(slots) - aired, (len(slots) - aired) // per_day))
    print("  %d have never aired" % never)
    print("  -> data/schedule.json (%.1f KB)" % (os.path.getsize(SCHED) / 1024))


if __name__ == "__main__":
    main()
