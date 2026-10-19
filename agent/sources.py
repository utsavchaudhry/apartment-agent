"""Fetch + parse rental portals. No LLM, no browser.

  * Kleinanzeigen  -- where most private Munich landlords actually post
  * WG-Gesucht     -- 1-Zimmer-Wohnungen and Wohnungen (private flats, not WG rooms)
  * ImmoScout24    -- via the app-facing API (the website sits behind DataDome)

Search locations come from settings ("sources"), so the dashboard can point the
agent at another town.
"""
import re, html, time, random, urllib.request
import config

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def online(timeout=5):
    """Is there actually a working connection right now?

    Resuming from suspend fires the catch-up scan before WiFi is back, which
    used to make every fetch fail silently and look like a quiet market.
    """
    for probe in ("https://www.kleinanzeigen.de/robots.txt",
                  "https://one.one.one.one/"):
        try:
            req = urllib.request.Request(probe, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout):
                return True
        except Exception:
            continue
    return False


def wait_for_network(max_wait=180):
    """Block until the network answers, or give up. Returns True if online."""
    waited = 0
    while waited < max_wait:
        if online():
            return True
        time.sleep(10)
        waited += 10
    return online()


def get(url, timeout=30, tries=3):
    """A polite GET with backoff. Returns '' only after genuinely retrying."""
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if attempt == tries - 1:
                return ""
            time.sleep(2 ** attempt + random.uniform(0, 1.5))
    return ""


def _clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _num(s):
    """'1.234,56 EUR' -> 1234.56

    Unescape FIRST: raw '55 m&sup2;' would otherwise strip down to '552'.
    """
    if not s:
        return None
    s = html.unescape(s)
    s = re.sub(r"[^\d,.]", "", s)
    if not s:
        return None
    # German format: dot = thousands, comma = decimal
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _grp(pat, text, flags=0, n=1):
    m = re.search(pat, text, flags)
    return m.group(n) if m else ""


# ------------------------------------------------------------- Kleinanzeigen
# location_id l6303 = "Garching b Muenchen - Kr. Muenchen"; find yours by running
# a search on kleinanzeigen.de and copying the "l1234" part of the URL.
KA = ("https://www.kleinanzeigen.de/s-wohnung-mieten/{slug}/"
      "{page}anzeige:angebote/preis::{maxp}/c203{loc}r{radius}")


def kleinanzeigen(max_price=1300):
    o = config.SOURCES["kleinanzeigen"]
    out = []
    for p in range(1, int(o.get("pages", 2)) + 1):
        url = KA.format(slug=o["location_slug"], loc=o["location_id"],
                        page="" if p == 1 else f"seite:{p}/",
                        maxp=max_price, radius=o.get("radius_km", 15))
        doc = get(url)
        if not doc:
            break
        for m in re.finditer(
                r'<article[^>]*data-adid="(\d+)"[^>]*data-href="([^"]+)".*?</article>',
                doc, re.S):
            adid, href, blk = m.group(1), m.group(2), m.group(0)
            blk = re.sub(r"<script.*?</script>", " ", blk, flags=re.S)
            blk = re.sub(r"<svg.*?</svg>", " ", blk, flags=re.S)

            title = _clean(_grp(r"<h3[^>]*>(.*?)</h3>", blk, re.S))
            price = _num(_grp(r'text-title3 font-strong text-secondary">([^<]+)<', blk))
            attrs = _clean(_grp(r'font-strong text-onSurfaceSubdued">([^<]*)<', blk))
            desc = _clean(_grp(r'text-bodyRegular text-onSurfaceSubdued">(.*?)</p>', blk, re.S))
            loc = _clean(_grp(r"<span>(\d{5}\s+[^<]+)</span>", blk))

            out.append(dict(
                uid=f"ka:{adid}",
                source="Kleinanzeigen",
                url="https://www.kleinanzeigen.de" + href,
                title=title,
                price=price,
                sqm=_num(_grp(r"([\d.,]+)\s*m²", attrs)),
                rooms=_num(_grp(r"([\d.,]+)\s*Zi", attrs)),
                loc=loc,
                avail="",
                body=" | ".join(x for x in (title, attrs, desc, loc) if x),
            ))
        time.sleep(random.uniform(3.0, 6.0))
    return out


# ---------------------------------------------------------------- WG-Gesucht
# Category 2 = 1-Zimmer-Wohnungen, 3 = Wohnungen. WG rooms are category 0 and
# are deliberately NOT fetched -- this agent looks for a place of your own.
# City 90 = Muenchen; the id is the number after the city name in any
# wg-gesucht.de search URL.
WG_PAGES = [
    "https://www.wg-gesucht.de/1-zimmer-wohnungen-in-{slug}.{cid}.2.1.{p}.html",
    "https://www.wg-gesucht.de/wohnungen-in-{slug}.{cid}.3.1.{p}.html",
]


def wggesucht(max_price=1300):
    o = config.SOURCES["wggesucht"]
    out = []
    for tmpl in WG_PAGES:
        for p in range(0, int(o.get("pages", 2))):
            tmpl_p = tmpl.format(slug=o["city_slug"], cid=o["city_id"], p="{p}")
            doc = get(tmpl_p.format(p=p))
            if not doc:
                break
            cards = re.split(r'(?=<div[^>]+id="liste-details-ad-\d+")', doc)
            for blk in cards:
                oid = _grp(r'id="liste-details-ad-(\d+)"', blk)
                if not oid:
                    continue
                blk = re.sub(r"<svg.*?</svg>", " ", blk, flags=re.S)

                title = _clean(_grp(r'<h2 class="truncate_title[^"]*">(.*?)</h2>', blk, re.S))
                sub = _clean(_grp(r'<div class="col-xs-11[^"]*">\s*<span[^>]*>(.*?)</span>', blk, re.S))
                price = _num(_grp(r'<div class="col-xs-3">\s*<b>([^<]+)</b>', blk, re.S))
                sqm = _num(_grp(r'<div class="col-xs-3 text-right">\s*<b>([^<]+)</b>', blk, re.S))
                avail = _clean(_grp(r'<div class="col-xs-5 text-center">(.*?)</div>', blk, re.S))

                href = _grp(r'href="(/[^"]*\.\d{6,}\.html)"', blk)
                if href:
                    href = "https://www.wg-gesucht.de" + href

                rooms = _num(_grp(r"(\d+)-Zimmer", sub)) or 1.0

                out.append(dict(
                    uid=f"wg:{oid}",
                    source="WG-Gesucht",
                    url=href,
                    title=title,
                    price=price,
                    sqm=sqm,
                    rooms=rooms,
                    loc=sub,
                    avail=avail,
                    body=" | ".join(x for x in (title, sub, avail) if x),
                ))
            time.sleep(random.uniform(3.0, 6.0))

    seen, uniq = set(), []
    for r in out:
        if r["uid"] in seen:
            continue
        seen.add(r["uid"])
        uniq.append(r)
    return uniq


ALL = [
    ("Kleinanzeigen", "kleinanzeigen", kleinanzeigen),
    ("WG-Gesucht", "wggesucht", wggesucht),
]


# ------------------------------------------------------------------- details
# Teasers hide the move-in date. For anything that survives the cheap filters we
# fetch the ad page itself, which carries "Verfuegbar ab" and the posting date.
def detail(url):
    """-> dict(avail, posted, deposit, text) — empty dict if unreachable."""
    if not url:
        return {}
    out = {}

    # Handled before the HTTP fetch below: DataDome blocks that fetch
    # outright, so reaching this branch through it is impossible.
    if "immobilienscout24.de" in url:
        # Exposes sit behind DataDome, so the HTML is unreachable -- but the
        # app-facing endpoint the search already uses serves the same record.
        # Without this branch the description was never read at all, so a body
        # saying "zeitlich befristet" reached no BLOCK_TERM: listing 171326159
        # scored MAYBE 62 on 30.09.2026 and only a human caught it.
        m = re.search(r"/expose/(\d+)", url)
        if not m:
            return out
        try:
            from immoscout import ImmoscoutClient
            e = ImmoscoutClient().get_expose(m.group(1))
        except Exception:
            return out          # optional dependency / transient failure
        out["text"] = (getattr(e, "description", "") or "")[:4000]
        attrs = getattr(e, "attributes", None) or {}
        if attrs.get("Bezugsfrei ab"):
            out["avail"] = attrs["Bezugsfrei ab"]
        # "Warmmiete" is often "keine Angabe" while "Gesamtmiete" is filled.
        warm = _num(attrs.get("Gesamtmiete") or "") or _num(attrs.get("Warmmiete") or "")
        if warm:
            out["warm"] = warm

        return out

    doc = get(url)
    if not doc:
        return {}

    if "kleinanzeigen.de" in url:
        # Label and value are separate nodes: "Wohnfläche<span ...>21 m²</span>".
        # Splitting the flattened text on whitespace gets "Verfügbar ab" wrong.
        attrs = {}
        for m in re.finditer(
                r'<li class="addetailslist--detail">\s*(.*?)\s*'
                r'<span class="addetailslist--detail--value"[^>]*>(.*?)</span>',
                doc, re.S):
            attrs[_clean(m.group(1))] = _clean(m.group(2))
        out["avail"] = attrs.get("Verfügbar ab", "")
        out["deposit"] = _num(attrs.get("Kaution / Genoss.-Anteile", ""))
        out["warm"] = _num(attrs.get("Warmmiete", ""))
        sm = re.search(r"Aktiv seit\s*(\d{2}\.\d{2}\.\d{4})", doc)
        if sm:
            out["seller_since"] = sm.group(1)
        pm = re.search(r'id="viewad-extra-info".*?(\d{2}\.\d{2}\.\d{4})', doc, re.S)
        if pm:
            out["posted"] = pm.group(1)
        dm = re.search(r'id="viewad-description-text"[^>]*>(.*?)</p>', doc, re.S)
        if dm:
            out["text"] = _clean(re.sub(r"<br\s*/?>", " \n ", dm.group(1)))[:4000]

    elif "wg-gesucht.de" in url:
        dm = re.search(r'id="ad_description_text"(.*?)</div>', doc, re.S)
        if dm:
            out["text"] = _clean(dm.group(1))[:4000]
        flat = _clean(doc)
        am = re.search(r"frei ab[:\s]*([\d.]{8,10})", flat, re.I)
        # "frei bis" marks a fixed term. Keeping only "frei ab" made a 6-week
        # sublet (01.12.2026 - 15.01.2027) score as an open-ended HIT, because
        # move_in_verdict only calls it fixed when it sees two dates.
        bm = re.search(r"frei bis[:\s]*([\d.]{8,10})", flat, re.I)
        if am and bm:
            out["avail"] = f"{am.group(1)} - {bm.group(1)}"
        elif am:
            out["avail"] = am.group(1)

    return out


# ------------------------------------------------------------------ ImmoScout
# ImmoScout is the biggest portal but sits behind DataDome, so plain scraping
# only earns CAPTCHAs. The unofficial `immoscout` client reaches the same data
# through the app-facing endpoint. It is a third-party package, so it is treated
# as optional: if the import fails the scan simply runs without this source.
#
# Only the regions in settings are queried, not all of Munich -- a city-wide
# search returns >1100 hits, almost all of them far outside the commute band.


def _rel_date(s):
    """'vor 10 Tagen' / 'Heute' / 'vor 7 Monaten' -> ISO date, best effort."""
    import datetime
    if not s:
        return ""
    t = s.lower().strip()
    today = datetime.date.today()
    if "heute" in t or "stunde" in t or "minute" in t:
        return str(today)
    if "gestern" in t:
        return str(today - datetime.timedelta(days=1))
    m = re.search(r"vor\s+(einem|einer|\d+)\s*(tag|tagen|woche|wochen|monat|monaten|jahr|jahren)", t)
    if not m:
        return ""
    n = 1 if m.group(1) in ("einem", "einer") else int(m.group(1))
    unit = m.group(2)
    days = {"tag": 1, "tagen": 1, "woche": 7, "wochen": 7,
            "monat": 30, "monaten": 30, "jahr": 365, "jahren": 365}[unit]
    return str(today - datetime.timedelta(days=n * days))


def immoscout24(max_price=1300):
    """Query only the configured regions (settings: sources.immoscout24.regions)."""
    o = config.SOURCES["immoscout24"]
    per_region = int(o.get("per_region", 50))
    try:
        from immoscout import ImmoscoutClient, SearchFilter
    except Exception:
        return []          # optional dependency; scan runs without this source

    try:
        client = ImmoscoutClient()
    except Exception:
        return []

    out = []
    for region in o.get("regions", []):
        try:
            flt = SearchFilter(region=region, real_estate_type="apartmentrent",
                               price_max=float(max_price))
            listings = list(client.search_all(flt, max_pages=2))[:per_region]
        except Exception:
            continue

        for lst in listings:
            addr = lst.address
            line = getattr(addr, "line", "") or ""
            out.append(dict(
                uid=f"is24:{lst.id}",
                source="ImmoScout24",
                url=lst.url or f"https://www.immobilienscout24.de/expose/{lst.id}",
                title=lst.title or "",
                price=lst.price,
                sqm=lst.living_space,
                rooms=lst.rooms,
                loc=line,
                avail="",
                posted=_rel_date(lst.published or ""),
                body=" | ".join(x for x in (lst.title or "", line,
                                            "privater Anbieter" if lst.is_private else "") if x),
            ))
        time.sleep(random.uniform(2.0, 4.0))

    seen, uniq = set(), []
    for r in out:
        if r["uid"] in seen:
            continue
        seen.add(r["uid"])
        uniq.append(r)
    return uniq


ALL.append(("ImmoScout24", "immoscout24", immoscout24))


def enabled():
    """[(name, fn)] for every source switched on in settings."""
    return [(name, fn) for name, key, fn in ALL
            if config.SOURCES.get(key, {}).get("enabled", True)]
