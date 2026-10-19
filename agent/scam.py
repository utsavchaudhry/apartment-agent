"""Flag rental scams and junk listings.

Munich has a busy fake-listing trade. The pattern is consistent: a flat priced
far below market, an owner who is conveniently abroad, keys "by post", and money
or documents wanted before anyone views anything. None of these are subtle, and
all of them are checkable in the ad text.

Returns (risk 0-100, flags). Anything >= 50 must not be contacted.
"""
import re, datetime
import config

UML = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _n(s):
    return (s or "").translate(UML).lower()


# (pattern, points, human explanation)
SIGNALS = [
    # money up front -- the actual payload of the scam
    (r"\bvorkasse|\banzahlung|\bkaution im voraus|\bkaution vorab|deposit in advance",
     40, "asks for money up front"),
    (r"western union|moneygram|\bbitcoin|\bcrypto|paypal.{0,15}(freund|family)",
     45, "untraceable payment method"),
    (r"\btreuhand|escrow|airbnb.{0,25}(zahlung|garantie)|notar.{0,20}(zahlung|treuhand)",
     35, "fake escrow / trustee arrangement"),

    # the absent landlord. Scored low on its own: in a university city the most
    # common reason for a Nachmieter ad is the current tenant leaving to study
    # abroad, which is the opposite of fraud. What makes "abroad" damning is
    # that it is offered as the reason no viewing is possible -- and that is
    # caught by the viewing and keys-by-post signals below, which stack on top.
    (r"im ausland|abroad|nicht in deutschland|derzeit in (england|london|uk|usa|amerika)",
     10, "mentions being abroad"),
    (r"schluessel per post|keys by post|schluessel.{0,20}(zusenden|versenden|post)",
     45, "keys to be sent by post"),
    (r"besichtigung (ist )?(leider )?nicht moeglich|no viewing possible|ohne besichtigung",
     40, "no viewing offered"),

    # documents before contact
    (r"(kopie|scan).{0,30}(ausweis|reisepass|passport).{0,40}(vorab|zuerst|bevor)",
     35, "wants ID documents before any viewing"),

    # tone and language markers common to the template scams
    (r"\bgott\b|\bgod bless|gesegnet|blessing", 20, "religious framing (common in these scams)"),
    (r"ich bin (ein )?(ehrlich|gottesfuerchtig)", 25, "unprompted claims of honesty"),

    # contact funnelling off-platform
    (r"nur per (e-?mail|whatsapp)|contact me (only )?(via|by) e-?mail",
     15, "pushes contact off the platform immediately"),

    # junk rather than fraud
    # "PROVISIONSFREI VON PRIVAT" says there is no commission, so matching
    # "provision" inside it flagged the exact thing we want. Same for
    # "ohne Provision" / "keine Courtage".
    (r"(?<!ohne )(?<!keine )(?:provision(?!s?frei)|courtage(?!frei)|maklergebuehr)",
     10, "agent commission payable"),
    (r"nachmieter gesucht.{0,40}abloese|abstand(szahlung)?", 15, "key money / Abloese demanded"),
]


# Phrasings that explain an "abroad" mention innocently: it is the departing
# tenant who is leaving, and they are still here to hand the flat over.
ABROAD_EXEMPT = re.compile(
    r"studium im ausland|auslandssemester|auslandsjahr|study (program|programme|abroad)"
    r"|semester abroad|ziehe ins ausland|gehe ins ausland|verlasse muenchen"
    r"|leaving munich|i am the current tenant|ich bin (der|die) (jetzige|derzeitige) mieter"
    r"|bin selbst mieter"
)


_CITY_PLZ = re.compile(r"\b8[01]\d{3}\b")


def _in_munich_city(rec):
    """Munich city postcodes are 80xxx/81xxx; the suburbs are 85xxx."""
    where = f"{rec.get('plz') or ''} {rec.get('loc') or ''} {rec.get('title') or ''}"
    # WG-Gesucht is only searched inside Munich city, and its teasers often
    # carry a district name but no postcode.
    return bool(_CITY_PLZ.search(where)) or rec.get("source") == "WG-Gesucht"


def _parse_date(s):
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", s)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def assess(rec, text=""):
    """rec is a listing dict; text is the full ad body if it has been fetched."""
    blob = _n(" ".join(str(rec.get(k, "")) for k in ("title", "body", "loc")) + " " + text)
    risk, flags = 0, []

    for pat, pts, why in SIGNALS:
        if re.search(pat, blob):
            if why == "mentions being abroad" and ABROAD_EXEMPT.search(blob):
                continue
            risk += pts
            flags.append(why)

    # Price far below market is the lure. Every scam the agent let through in
    # October 2026 advertised a furnished 45-92 m2 flat in Munich city for
    # EUR 485-900 (8.6-14.3 EUR/m2), while every genuine flat he dealt with was
    # 15+ EUR/m2 even on cold rent, and 19+ on warm. Suburbs (Eching,
    # Oberschleissheim) are genuinely cheaper, so they get their own floor.
    price, sqm = rec.get("price"), rec.get("sqm")
    basis = rec.get("warm") or price
    if price and not rec.get("warm") and rec.get("source") in getattr(config, "ESTIMATE_WARM_FOR", ()):
        # ImmoScout reports cold rent; compare on the same all-in footing.
        basis = price + config.NEBENKOSTEN_BASE + (sqm or 30) * config.NEBENKOSTEN_PER_SQM
    city = _in_munich_city(rec)
    if basis and sqm and sqm >= 15:
        per_sqm = basis / sqm
        if city:
            scam_below, suspect_below, where = (config.SCAM_CITY_EUR_M2,
                                                config.SUSPECT_CITY_EUR_M2, "central Munich")
        else:
            scam_below, suspect_below, where = (config.SCAM_SUBURB_EUR_M2,
                                                config.SUSPECT_SUBURB_EUR_M2, "this area")
        if per_sqm < scam_below:
            risk += 50
            flags.append(f"{per_sqm:.1f} EUR/m2 — far below any real rent in {where}")
        elif per_sqm < suspect_below:
            risk += 25
            flags.append(f"{per_sqm:.1f} EUR/m2 — suspiciously cheap for {where}")

        # The bait shape: a big central flat for the price of a studio.
        if city and sqm >= 55 and basis < 1000:
            risk += 30
            flags.append(f"{sqm:.0f} m2 in central Munich for {basis:.0f} EUR — implausible")
        # Furnished commands a premium in Munich; cheap AND furnished is the scam template.
        if city and per_sqm < 20 and re.search(r"m(oe|ö)bliert", blob):
            risk += 15
            flags.append("furnished yet cheap")

    # Scams run on throwaway or hijacked accounts. Read off the ad page.
    since = _parse_date(rec.get("seller_since") or "")
    if since:
        age = (datetime.date.today() - since).days
        if age < config.NEW_SELLER_DAYS:
            risk += 40
            flags.append(f"seller account only {age} days old")
        elif age < 180:
            risk += 10
            flags.append(f"seller account {age} days old")

    return min(100, risk), flags


def verdict(risk):
    if risk >= 50:
        return "SCAM"
    if risk >= 25:
        return "SUSPECT"
    return "OK"
