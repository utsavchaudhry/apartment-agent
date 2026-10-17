"""Flag rental scams and junk listings.

Munich has a busy fake-listing trade. The pattern is consistent: a flat priced
far below market, an owner who is conveniently abroad, keys "by post", and money
or documents wanted before anyone views anything. None of these are subtle, and
all of them are checkable in the ad text.

Returns (risk 0-100, flags). Anything >= 50 must not be contacted.
"""
import re

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

    # Price far below market is the lure. Munich warm rent is roughly
    # 25-35 EUR/m2; under 12 EUR/m2 is not a bargain, it is bait.
    price, sqm = rec.get("price"), rec.get("sqm")
    if price and sqm and sqm >= 15:
        per_sqm = price / sqm
        if per_sqm < 8:
            risk += 45
            flags.append(f"{per_sqm:.0f} EUR/m2 — far below any real Munich rent")
        elif per_sqm < 12:
            risk += 25
            flags.append(f"{per_sqm:.0f} EUR/m2 — suspiciously cheap")

    # A big flat at a tiny price is the classic bait shape
    if price and sqm and sqm >= 60 and price <= 700:
        risk += 30
        flags.append(f"{sqm:.0f} m2 for {price:.0f} EUR — implausible")

    return min(100, risk), flags


def verdict(risk):
    if risk >= 50:
        return "SCAM"
    if risk >= 25:
        return "SUSPECT"
    return "OK"
