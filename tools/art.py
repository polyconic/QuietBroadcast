#!/usr/bin/env python3
"""Pull sleeve art for every scheduled record into art/, and record the filename
on each entry in data/schedule.json.

The URLs come out of the local album.getInfo cache, so this makes no Last.fm API
calls. Images are downloaded once and served from the repo - the site never asks
a third party for anything at runtime.
"""
import glob, hashlib, json, os, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, ".cache")
ART = os.path.join(HERE, "art")
SCHED = os.path.join(DATA, "schedule.json")

# Last.fm's placeholder star, served when a release has no real sleeve.
PLACEHOLDER = "2a96cbd8b46e442fc41c2b86b821562f"
ORDER = ("mega", "extralarge", "large", "medium")


def candidates(images):
    """Largest first. Last.fm 404s the big sizes for some releases, so keep the
    smaller ones as fallbacks rather than giving up on the sleeve."""
    by = {i.get("size"): i.get("#text") for i in images if i.get("#text")}
    out = []
    for s in ORDER:
        u = by.get(s)
        if u and PLACEHOLDER not in u and u not in out:
            out.append(u)
    return out


def url_map():
    out = {}
    for f in glob.glob(os.path.join(CACHE, "*.json")):
        if os.path.basename(f).startswith("artist--"):
            continue
        try:
            a = (json.load(open(f)).get("album") or {})
        except Exception:
            continue
        if not a.get("name"):
            continue
        us = candidates(a.get("image") or [])
        if us:
            out[(a.get("artist", ""), a["name"])] = us
    return out


def main():
    if not os.path.exists(SCHED):
        sys.exit("No data/schedule.json - run tools/schedule.py first.")
    sched = json.load(open(SCHED))
    urls = url_map()
    os.makedirs(ART, exist_ok=True)

    jobs, miss = [], 0
    for r in sched["records"]:
        us = urls.get((r["artist"], r["release"]))
        if not us:
            r["art"] = ""
            miss += 1
            continue
        u = us[0]
        ext = os.path.splitext(u)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            ext = ".jpg"
        name = hashlib.sha1(u.encode()).hexdigest()[:16] + ext
        r["art"] = "art/" + name
        if not os.path.exists(os.path.join(ART, name)):
            jobs.append((r, us, os.path.join(ART, name)))

    print("  %d sleeves to fetch (%d already local, %d have none)"
          % (len(jobs), len(sched["records"]) - len(jobs) - miss, miss), flush=True)

    failed = []

    def grab(job):
        r, us, path = job
        last = None
        for u in us:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "NodeRecord/1.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    blob = resp.read()
                if len(blob) < 500:
                    raise ValueError("suspiciously small")
                open(path, "wb").write(blob)
                return
            except Exception as e:
                last = e
        failed.append((r, last))
        r["art"] = ""

    with ThreadPoolExecutor(max_workers=12) as pool:
        for i, _ in enumerate(pool.map(grab, jobs), 1):
            if i % 100 == 0:
                print("    %d/%d" % (i, len(jobs)), flush=True)

    for r, e in failed[:5]:
        print("    ! %s - %s (%s)" % (r["artist"], r["release"], e))
    fetched = len(jobs) - len(failed)
    failed = len(failed)

    json.dump(sched, open(SCHED, "w"), ensure_ascii=False, separators=(",", ":"))
    total = sum(os.path.getsize(os.path.join(ART, f)) for f in os.listdir(ART))
    withart = sum(1 for r in sched["records"] if r.get("art"))
    print("\n  %d of %d records have a sleeve (%d had none on Last.fm, %d failed)"
          % (withart, len(sched["records"]), miss, failed))
    print("  %d downloaded this run, art/ is %.1f MB" % (fetched, total / 1e6))


if __name__ == "__main__":
    main()
