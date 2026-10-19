"""Score a listing against the criteria in config.py. Pure functions, no I/O."""
import re, datetime, functools
import config

# Ads are full of typographic punctuation that looks identical to the ASCII
# kind and matches none of it. "WG\u2011Zimmer" with a NON-BREAKING HYPHEN sailed
# past the "wg-zimmer" block on 15.10.2026 and scored a shared room as a HIT.
# 100 titles in the corpus use one of these characters, so fold them all here
# rather than per-term: the soft hyphen is invisible and simply goes away.
UML = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                     "Ä": "ae", "Ö": "oe", "Ü": "ue",
                     "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
                     "\u2014": "-", "\u2015": "-", "\u2212": "-", "\u00ad": "",
                     "\u00a0": " ", "\u202f": " ", "\u2019": "'", "\u2018": "'"})


def norm(s):
    return (s or "").translate(UML).lower()


@functools.lru_cache(maxsize=None)
def _term_re(term):
    """A block term as a whole-word pattern.

    Substring matching was silently poisoning the filter: "befristet" fired on
    "unbefristet" -- the exact contract you want -- and "tage" fired on
    "Etagenwohnung". Word boundaries are only added where the term actually
    starts or ends with a word character, so "wg!" still works.
    """
    t = norm(term)
    pat = re.escape(t).replace(r"\ ", r"\s+")
    if t[:1].isalnum():
        pat = r"\b" + pat
    if t[-1:].isalnum():
        pat = pat + r"\b"
    return re.compile(pat)


def blocked_by(terms, text):
    """-> the first term that matches, or None."""
    for term in terms:
        if _term_re(term).search(text):
            return term
    return None


# "nach X" / "Richtung X" name somewhere the flat is NOT -- and the name often
# sits further down an enumeration ("nach Dachau, Garching und Unterschleissheim"),
# so the whole clause after the preposition counts. "zur"/"zum" are deliberately
# absent: "3 Gehminuten zur U-Bahn Alte Heide" is the proximity claim we want.
_DEST = re.compile(r"\b(?:nach|richtung)\b[^.;!?|]{0,90}")


def _only_as_destination(station, text):
    """True if every mention of `station` sits in a 'nach ...' clause."""
    spans = [m.span() for m in _DEST.finditer(text)]
    for m in re.finditer(re.escape(station), text):
        if not any(a <= m.start() < b for a, b in spans):
            return False          # at least one mention is a location claim
    return True


# A tenant advertising for a flat, not a flat on offer. The block term "gesuch"
# stopped catching these once terms became whole-word: "gesucht" is not "gesuch".
# "Gesucht wird eine Wohnung" was the only shape caught until 13.10.2026, when
# "Vermieter mit Herz gesucht" scored 100 and was saved only by its postcode --
# so the plain "<dwelling> gesucht" and "suche <dwelling>" shapes count too.
#
# Everything turns on WHO is being sought. A landlord looking for a *Mieter*,
# *Nachmieter* or *Untermieter* is the real offer we most want to see, so that
# wins outright -- otherwise "Nachmieter fuer 2-Zimmer-Wohnung gesucht" would
# read as a wanted ad. \b before "mieter" leaves "Vermieter" alone, which is
# the opposite party and belongs with the seekers.
_OFFERING = re.compile(r"\b(?:nach|unter|zwischen)?mieter(?:in)?\b|\bnachfolger")
_SEEKING = re.compile(
    r"\bgesucht\s+wird\s+(?:ein|eine)\b[^.;!?|]{0,25}?"
    r"(?:wohnung|apartment|appartement|studio|zimmer)"
    r"|(?:wohnung|wohnraum|apartment|appartement|studio|bleibe|unterkunft|vermieter(?:in)?)"
    r"[^.;!?|]{0,30}?\bgesucht\b"
    r"|\b(?:suche|suchen)\b[^.;!?|]{0,30}?"
    r"(?:wohnung|apartment|appartement|studio|bleibe|unterkunft)")


def is_wanted_ad(headline):
    """True for 'Gesucht wird eine 1-Zimmer-Wohnung' / 'Vermieter gesucht'."""
    if _OFFERING.search(headline):
        return False
    return bool(_SEEKING.search(headline))


# "für zwei Wochen", "nur für 3 Monate" -- a sublet, not a home. The Glockenbach
# ad of 19.10.2026 ("für zwei Wochen vom 18.11.-02.12. unter") said neither
# "Zwischenmiete" nor "Untermiete" and scored a HIT. Months only count with
# "nur", so "Kaution für drei Monate" does not trip it.
_NUM = r"(?:\d+|ein|eine|einen|zwei|drei|vier|fuenf|sechs|sieben|acht|zehn|paar)"
_SHORT_LET = re.compile(
    r"\bfuer\s+(?:ca\.?\s+)?" + _NUM + r"\s+(?:tag|tage|nacht|naechte|woche|wochen)\b"
    r"|\bnur\s+(?:fuer\s+)?" + _NUM + r"\s+(?:monat|monate)\b")


MONTHS = {
    "januar": 1, "jan": 1, "februar": 2, "feb": 2, "maerz": 3, "marz": 3, "mar": 3,
    "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10,
    "okt": 10, "november": 11, "nov": 11, "dezember": 12, "dez": 12,
}


def parse_dates(text):
    """Every date we can find, as date objects, in order of appearance."""
    out = []
    t = norm(text)
    # ISO first: sources that report a relative age ("vor 7 Monaten") are
    # normalised to YYYY-MM-DD, which the German DD.MM.YYYY pattern misses.
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", t):
        y, mo, d = (int(x) for x in m.groups())
        try:
            out.append(datetime.date(y, mo, d))
        except ValueError:
            pass
    for m in re.finditer(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{2,4})\b", t):
        d, mo, y = (int(x) for x in m.groups())
        y = y + 2000 if y < 100 else y
        try:
            out.append(datetime.date(y, mo, d))
        except ValueError:
            pass
    for m in re.finditer(r"\b(\d{1,2})\.?\s*([a-z]{3,9})\.?\s*(\d{4})\b", t):
        d, mon, y = m.group(1), m.group(2), m.group(3)
        if mon in MONTHS:
            try:
                out.append(datetime.date(int(y), MONTHS[mon], int(d)))
            except ValueError:
                pass
    for m in re.finditer(r"\b([a-z]{3,9})\s+(\d{4})\b", t):
        mon, y = m.group(1), m.group(2)
        if mon in MONTHS:
            try:
                out.append(datetime.date(int(y), MONTHS[mon], 1))
            except ValueError:
                pass
    return out


def move_in_verdict(rec):
    """(status, date_or_None, note). status in ok | early | late | fixed | unknown"""
    # An empty window means "from today, for the next six months".
    today = datetime.date.today()
    earliest = (datetime.date.fromisoformat(config.MOVE_IN_EARLIEST)
                if config.MOVE_IN_EARLIEST else today)
    latest = (datetime.date.fromisoformat(config.MOVE_IN_LATEST)
              if config.MOVE_IN_LATEST else today + datetime.timedelta(days=183))
    avail = rec.get("avail") or ""
    body = rec.get("body") or ""

    # WG-Gesucht gives "01.10.2026" or "20.09.2026 - 31.12.2026" (a fixed term)
    if avail:
        ds = parse_dates(avail)
        if len(ds) >= 2:
            return "fixed", ds[0], f"fixed term {ds[0]} to {ds[1]}"
        if len(ds) == 1:
            d = ds[0]
            if d < earliest:
                return "early", d, f"available {d}, months before you need it"
            if d > latest:
                return "late", d, f"available {d}, too late"
            return "ok", d, f"available {d}"

    t = norm(body)
    m = re.search(r"(?:frei|verfuegbar|bezugsfrei|einzug|ab)\s*(?:ab\s*)?"
                  r"(\d{1,2}\.\s*\d{1,2}\.\s*\d{2,4})", t)
    if m:
        ds = parse_dates(m.group(1))
        if ds:
            d = ds[0]
            if d < earliest:
                return "early", d, f"available {d}"
            if d > latest:
                return "late", d, f"available {d}"
            return "ok", d, f"available {d}"

    if re.search(r"\bab sofort\b|\bsofort bezieh|\bab heute\b", t):
        return "early", None, "advertised 'ab sofort' -- may be gone before you can move"
    return "unknown", None, "no move-in date in the teaser; open the ad"


def evaluate(rec):
    """-> (score:int, verdict:str, reasons:list[str])"""
    reasons = []
    text = norm(f"{rec.get('title','')} {rec.get('body','')} {rec.get('loc','')}")
    # The title says what is being offered; the description merely describes it.
    headline = norm(f"{rec.get('title','')} {rec.get('loc','')}")

    # ---- hard blocks -------------------------------------------------
    term = blocked_by(config.BLOCK_TERMS, text)
    if term:
        return 0, "REJECT", [f"blocked term: '{term}'"]
    term = blocked_by(getattr(config, "BLOCK_TERMS_TITLE", ()), headline)
    if term:
        return 0, "REJECT", [f"not an offer of a flat -- title says '{term}'"]
    if is_wanted_ad(headline):
        return 0, "REJECT", ["a tenant looking for a flat, not a flat on offer"]
    short = _SHORT_LET.search(text)
    if short:
        return 0, "REJECT", [f"short-term let: '{short.group(0)}'"]

    price = rec.get("price")
    sqm_for_est = rec.get("sqm")
    est_warm = None
    # A warm rent read off the ad page beats any estimate. Both Kleinanzeigen
    # and ImmoScout report one once the detail page has been fetched.
    real_warm = rec.get("warm")
    if real_warm:
        est_warm = float(real_warm)
    elif price is not None and rec.get("source") in getattr(config, "ESTIMATE_WARM_FOR", ()):
        # price here is Kaltmiete; approximate the all-in figure
        # Observed real gaps: 56m2 +220, 43m2 +160, 32m2 +300, 24m2 +258.
        # A pure per-m2 model underestimates small furnished flats badly, so
        # use a flat base plus a per-m2 term.
        extra = (getattr(config, "NEBENKOSTEN_BASE", 100.0)
                 + (sqm_for_est or 30) * getattr(config, "NEBENKOSTEN_PER_SQM", 4.0))
        est_warm = price + extra

    # A placeholder price ("1 EUR VB") is an absence of information, not a
    # bargain; treating it as one handed a 50 m2 attic room a 75 score.
    if price is not None and price < getattr(config, "MIN_PLAUSIBLE_RENT", 250):
        price = est_warm = None

    check_price = est_warm if est_warm is not None else price
    if price is None:
        reasons.append("no real price given -- ad says VB / nach Absprache")
    elif check_price > config.MAX_RENT_WARM:
        if est_warm is not None:
            how = "laut Anzeige" if real_warm else "est."
            return 0, "REJECT", [f"{price:.0f} EUR kalt -> {est_warm:.0f} EUR warm ({how}), "
                                 f"over the {config.MAX_RENT_WARM} ceiling"]
        return 0, "REJECT", [f"{price:.0f} EUR over the {config.MAX_RENT_WARM} ceiling"]

    sqm = rec.get("sqm")
    if sqm is not None and sqm < config.MIN_SQM:
        return 0, "REJECT", [f"{sqm:.0f} m2 under the {config.MIN_SQM} m2 floor"]

    # ---- geography ---------------------------------------------------
    plz = ""
    m = re.search(r"\b(\d{5})\b", f"{rec.get('loc','')} {rec.get('title','')}")
    if m:
        plz = m.group(1)
    area, commute = config.PLZ_COMMUTE.get(plz, ("", None))

    if plz and commute is None:
        return 0, "REJECT", [f"PLZ {plz} is outside the U6 commute band"]
    if commute is not None and commute > config.MAX_COMMUTE_MIN:
        return 0, "REJECT", [f"{area}: ~{commute} min, over the {config.MAX_COMMUTE_MIN} min limit"]

    near_station = any(s in text for s in (norm(x) for x in config.GOOD_STATIONS))

    # A named U6 station beats the postcode guess: postcodes straddle lines.
    # Only where the ad places the flat *at* the station, though -- an
    # Oberschleissheim attic listing "Busverbindungen nach Dachau, Garching und
    # Unterschleissheim" scored 100 on a 16 min commute it does not have.
    named = [(norm(k), v) for k, v in getattr(config, "STATION_COMMUTE", {}).items()
             if norm(k) in text and not _only_as_destination(norm(k), text)]
    if named:
        best = min(named, key=lambda kv: kv[1])
        if commute is None or abs(best[1] - commute) > 3:
            commute = best[1]
            area = area or best[0]
            reasons.append(f"station '{best[0]}' in ad -> ~{best[1]} min (overrides postcode)")
        if commute > config.MAX_COMMUTE_MIN:
            return 0, "REJECT", [f"{best[0]}: ~{commute} min, over the "
                                 f"{config.MAX_COMMUTE_MIN} min limit"]
    else:
        # No U6 station named, but a different line is -> the postcode estimate
        # is not trustworthy. Milbertshofen (U2) sits in 80807 alongside
        # Nordfriedhof (U6) and is ~12 min further with two changes.
        wrong = [w for w in getattr(config, "WRONG_LINE", []) if norm(w) in text]
        if wrong:
            if getattr(config, "SINGLE_RIDE_ONLY", False):
                # You want ONE connection to the office. Any other line means a
                # change, which disqualifies it regardless of total minutes.
                return 0, "REJECT", [f"names {wrong[0]}: not a single ride to Garching "
                                     f"(would need a change)"]
            if commute is not None:
                commute += 12
                reasons.append(f"names {wrong[0]} (not U6) -> +12 min, ~{commute} min")
                if commute > config.MAX_COMMUTE_MIN:
                    return 0, "REJECT", [f"{wrong[0]}: ~{commute} min with changes, over limit"]

    if not plz and not near_station and not named:
        return 0, "REJECT", ["no postcode and no U6 reference -- location unverifiable"]

    # ---- timing ------------------------------------------------------
    mstatus, mdate, mnote = move_in_verdict(rec)
    if mstatus == "fixed":
        return 0, "REJECT", [f"not open-ended: {mnote}"]
    if mstatus == "late":
        return 0, "REJECT", [mnote]

    # A move-in date already in the past means a stale ad, not an early one.
    today = datetime.date.today()
    if mdate and mdate < today:
        return 0, "REJECT", [f"stale: advertised free from {mdate}, already past"]

    # Same for the posting date, when we have fetched the ad page.
    posted = rec.get("posted")
    if posted:
        pd = parse_dates(posted)
        if pd and (today - pd[0]).days > getattr(config, "STALE_AFTER_DAYS", 21):
            return 0, "REJECT", [f"stale: posted {pd[0]}, {(today - pd[0]).days} days ago"]

    # ---- score -------------------------------------------------------
    score = 50
    if est_warm is not None and price is not None:
        how = "laut Anzeige" if real_warm else "estimated"
        reasons.append(f"{price:.0f} EUR kalt -> {est_warm:.0f} EUR warm ({how})")
    if check_price is not None:
        price = check_price
        if price <= config.PREFER_UNDER:
            score += 25
            reasons.append(f"{price:.0f} EUR -- under the {config.PREFER_UNDER} target")
        else:
            span = config.MAX_RENT_WARM - config.PREFER_UNDER
            score += int(20 * (1 - (price - config.PREFER_UNDER) / span))
            reasons.append(f"{price:.0f} EUR")

    if commute is not None:
        if commute <= 16:
            score += 20
        elif commute <= 26:
            score += 12
        else:
            score += 5
        reasons.append(f"{area}, ~{commute} min door-to-door")
    elif near_station:
        score += 5
        reasons.append("mentions U6/U-Bahn but no postcode -- verify")

    if sqm:
        reasons.append(f"{sqm:.0f} m2")
        if sqm >= 25:
            score += 5

    if mstatus == "ok":
        score += 20
        reasons.append(mnote)
    elif mstatus == "early":
        score -= 10
        reasons.append(mnote)
    else:
        reasons.append(mnote)

    for term in config.SOFT_NEGATIVE:
        if _term_re(term).search(text):
            score -= 10
            reasons.append(f"note: '{term}'")

    score = max(0, min(100, score))
    # Never promote an ad to HIT while the rent is unknown -- HITs get pushed to
    # your phone the moment they are found, and "price on request" is not news.
    priced = check_price is not None
    verdict = "HIT" if (score >= 70 and priced and mstatus in ("ok", "unknown")) else "MAYBE"
    return score, verdict, reasons
