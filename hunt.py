"""Builds listings.json: Property Finder 1BHK yearly rentals (Dubai + Sharjah),
with true yearly cost and commute to Dubai Internet City.

Used by app.py (the dashboard). Can also be run directly:  python3 hunt.py [--refresh]
"""
import datetime, heapq, json, math, os, random, re, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
def path(*p): return os.path.join(HERE, *p)

MAX_RENT = 50000       # listed rent (true cost may be higher)
MAX_PAGES = {"Dubai": 40, "Sharjah": 4}   # ~25 listings/page; Dubai = all pages (~21)
DELAY = (6, 10)        # seconds between Property Finder requests
CITIES = {"Dubai": 1, "Sharjah": 4}   # Property Finder location ids
OFFICE = (25.1022, 55.1739)           # Dubai Internet City metro station
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

GOOGLE_MAX_CALLS = 300          # hard cap per run, to stay well inside the free tier
DEPART = (7, 45)                # leave home at 07:45 on the next weekday


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


# ---- Property Finder ----------------------------------------------------
def fetch_page(city_id, page, refresh):
    cache = path("cache", f"pf_{city_id}_{page}.json")
    if os.path.exists(cache) and not refresh:
        return json.load(open(cache)), False
    url = (f"https://www.propertyfinder.ae/en/search?c=2&bdr%5B%5D=1&rp=y"
           f"&l={city_id}&pt={MAX_RENT}&page={page}")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError(f"Property Finder returned no data on page {page} (blocked or captcha?)")
    data = json.loads(m.group(1))["props"]["pageProps"]["searchResult"]
    os.makedirs(path("cache"), exist_ok=True)
    json.dump(data, open(cache, "w"))
    return data, True


def chiller(desc):
    d = desc.lower()
    if re.search(r"(chiller|cooling)[\s-]*(free|included)|free[\s-]*(chiller|cooling)|(no|without)[\s-]*chiller", d):
        return "free"
    if "chiller" in d:
        return "mentioned"
    return ""


STUDIO_TITLE = re.compile(r"\bstudio\b(?!\s*city)", re.I)
STUDIO_DESC = re.compile(r"\b(this|a|the|our)\s+([\w-]+\s+){0,3}studio\b(?!\s*city)"
                         r"|\bstudio\s+(apartment\s+|flat\s+|unit\s+)?for\s+rent", re.I)


def is_studio(title, desc):
    """Agents often tag studios as '1 bed'. True when the ad itself calls the unit a studio."""
    return bool(STUDIO_TITLE.search(title or "") or STUDIO_DESC.search(desc or ""))


def true_cost(rent, city):
    if city == "Dubai":
        return rent * 1.05                 # 5% DEWA housing fee
    return rent + max(rent * 0.04, 500)    # Sharjah attestation fee 4%, min AED 500 (to verify)


# ---- free commute estimate (fallback when no Google key) ----------------
WALK_MAX_KM = 1.0; WALK_KMH = 4.5; ROAD_FACTOR = 1.35
FEEDER_KMH = 20; FEEDER_WAIT = 8
METRO_KM_PER_MIN = 0.75; DWELL = 0.5; BOARD_WAIT = 3; TRANSFER = 5; LAST_MILE = 5
METRO = json.load(open(path("metro.json")))


def _metro_minutes_to_dic():
    nodes = [(line, i) for line, st in METRO.items() for i in range(len(st))]
    pos = {n: (METRO[n[0]][n[1]]["lat"], METRO[n[0]][n[1]]["lon"]) for n in nodes}
    edges = {n: [] for n in nodes}
    for line, st in METRO.items():
        for i in range(len(st) - 1):
            a, b = (line, i), (line, i + 1)
            t = km(pos[a], pos[b]) / METRO_KM_PER_MIN + DWELL
            edges[a].append((b, t)); edges[b].append((a, t))
    for a in nodes:
        for b in nodes:
            if a[0] != b[0] and km(pos[a], pos[b]) < 0.3:
                same = a[0].startswith("Red") and b[0].startswith("Red")
                edges[a].append((b, 0 if same else TRANSFER))
    start = ("Red1", [s["name"] for s in METRO["Red1"]].index("Dubai Internet City"))
    dist, q = {start: 0}, [(0, start)]
    while q:
        d, n = heapq.heappop(q)
        if d > dist[n]:
            continue
        for m, t in edges[n]:
            if d + t < dist.get(m, 1e9):
                dist[m] = d + t; heapq.heappush(q, (d + t, m))
    best = {}
    for n, d in dist.items():
        s = METRO[n[0]][n[1]]
        if d < best.get(s["name"], (1e9,))[0]:
            best[s["name"]] = (d, (s["lat"], s["lon"]))
    return best


METRO_TO_DIC = _metro_minutes_to_dic()


def estimate_commute(lat, lon):
    best = None
    near = sorted((km((lat, lon), sp), n, ride) for n, (ride, sp) in METRO_TO_DIC.items())[:3]
    for d, name, ride in near:
        if d <= WALK_MAX_KM:
            feed, walk, how = d * ROAD_FACTOR / WALK_KMH * 60, d * ROAD_FACTOR / WALK_KMH * 60, "Walk"
        else:
            feed, walk, how = FEEDER_WAIT + d * ROAD_FACTOR / FEEDER_KMH * 60, 5, "Bus"
        total = feed + (BOARD_WAIT + ride if name != "Dubai Internet City" else 0) + LAST_MILE
        if best is None or total < best["minutes"]:
            best = {"minutes": round(total), "walk_min": round(walk + LAST_MILE),
                    "route": f"{how} → Metro ({name})", "source": "estimate"}
    return best


# ---- Google Routes API (transit) ----------------------------------------
def google_key():
    k = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not k and os.path.exists(path("google_key.txt")):
        k = open(path("google_key.txt")).read().strip()
    return k or None


def next_weekday_departure():
    dubai = datetime.timezone(datetime.timedelta(hours=4))
    d = datetime.datetime.now(dubai).date() + datetime.timedelta(days=1)
    while d.weekday() >= 5:            # UAE weekend: Sat, Sun
        d += datetime.timedelta(days=1)
    return datetime.datetime(d.year, d.month, d.day, *DEPART, tzinfo=dubai).isoformat()


def google_commute(lat, lon, key, depart):
    body = {
        "origin": {"location": {"latLng": {"latitude": lat, "longitude": lon}}},
        "destination": {"location": {"latLng": {"latitude": OFFICE[0], "longitude": OFFICE[1]}}},
        "travelMode": "TRANSIT",
        "departureTime": depart,
    }
    req = urllib.request.Request(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": key,
                 "X-Goog-FieldMask": "routes.duration,routes.legs.steps.travelMode,"
                                     "routes.legs.steps.staticDuration,"
                                     "routes.legs.steps.transitDetails.transitLine.nameShort,"
                                     "routes.legs.steps.transitDetails.transitLine.name,"
                                     "routes.legs.steps.transitDetails.transitLine.vehicle.type"})
    resp = json.load(urllib.request.urlopen(req, timeout=30))
    if not resp.get("routes"):
        return None
    r = resp["routes"][0]
    walk, parts = 0, []
    for leg in r["legs"]:
        for s in leg.get("steps", []):
            secs = int(s.get("staticDuration", "0s").rstrip("s"))
            if s.get("travelMode") == "WALK":
                walk += secs
                if not parts or parts[-1] != "Walk":
                    parts.append("Walk")
            elif s.get("transitDetails"):
                line = s["transitDetails"].get("transitLine", {})
                kind = {"SUBWAY": "Metro", "BUS": "Bus", "TRAM": "Tram", "INTERCITY_BUS": "Bus"}.get(
                    line.get("vehicle", {}).get("type"), "Transit")
                name = line.get("nameShort") or line.get("name") or ""
                name = {"MGrn": "Green", "MRed1": "Red", "MRed2": "Red"}.get(name, name)
                parts.append(f"{kind} {name}".strip())
    return {"minutes": round(int(r["duration"].rstrip("s")) / 60), "walk_min": round(walk / 60),
            "route": " → ".join(parts), "source": "google"}


# ---- build --------------------------------------------------------------
def build(refresh=False, log=print):
    rows, seen_ids = [], set()
    for city, cid in CITIES.items():
        for page in range(1, MAX_PAGES[city] + 1):
            data, fetched = fetch_page(cid, page, refresh)
            log(f"{city} page {page}: {len(data['listings'])} items{' (downloaded)' if fetched else ' (cached)'}")
            for item in data["listings"]:
                if item.get("listing_type") != "property":
                    continue
                p = item["property"]
                if p["id"] in seen_ids:     # promoted ads repeat across pages
                    continue
                seen_ids.add(p["id"])
                if p["price"]["period"] != "yearly" or p["bedrooms"] != "1" or p["price"]["value"] > MAX_RENT:
                    continue
                loc, rent = p["location"], p["price"]["value"]
                tree = [t["name"] for t in p["location_tree"]]
                rows.append({
                    "id": p["id"], "city": city,
                    "area": tree[1] if len(tree) > 1 else "",
                    "building": loc["name"],
                    "lat": loc["coordinates"]["lat"], "lon": loc["coordinates"]["lon"],
                    "rent": rent, "true_cost": round(true_cost(rent, city)),
                    "sqft": p["size"]["value"] if p.get("size") else None,
                    "cheques": p.get("number_of_cheques"),
                    "furnished": p.get("furnished", ""),
                    "chiller": chiller(p.get("description", "")),
                    "studio": is_studio(p.get("title"), p.get("description")),
                    "title": p.get("title", ""),
                    "image": (p.get("images") or [{}])[0].get("medium"),
                    "listed": p["listed_date"][:10],
                    "url": p["share_url"],
                })
            if fetched:
                time.sleep(random.uniform(*DELAY))
            if page >= data["meta"]["page_count"]:
                break

    # commute: Google if we have a key (cached per location), else estimate
    cache_file = path("commute_cache.json")
    cache = json.load(open(cache_file)) if os.path.exists(cache_file) else {}
    key, depart, calls = google_key(), next_weekday_departure(), 0
    log("Commute: " + ("Google Routes (transit, " + depart[:16] + ")" if key else "free estimate (no Google key)"))
    for r in rows:
        ck = f"{r['lat']:.4f},{r['lon']:.4f}"
        c = cache.get(ck)
        if not c and key and calls < GOOGLE_MAX_CALLS:
            calls += 1
            try:
                c = google_commute(r["lat"], r["lon"], key, depart)
            except Exception as e:
                log(f"Google error: {e}")
                key = None   # stop calling on errors (bad key, quota, ...)
            if key:   # remember "no route" too, so we don't pay to ask again
                cache[ck] = c or {"no_route": True}
        if c and not c.get("no_route"):
            r["commute"] = c
        else:
            r["commute"] = estimate_commute(r["lat"], r["lon"])
            if c:
                r["commute"]["route"] = "Google found no transit route · guess: " + r["commute"]["route"]
    json.dump(cache, open(cache_file, "w"))
    if calls:
        log(f"Google calls this run: {calls} (cap {GOOGLE_MAX_CALLS})")

    dubai_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=4)))
    out = {"updated": dubai_now.strftime("%Y-%m-%dT%H:%M"), "listings": rows}   # Dubai time, also on GitHub's servers
    json.dump(out, open(path("listings.json"), "w"))
    log(f"Done: {len(rows)} listings")
    return out


if __name__ == "__main__":
    build(refresh="--refresh" in sys.argv)
