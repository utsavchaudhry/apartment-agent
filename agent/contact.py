"""Build the enquiry message for a listing.

This module DRAFTS. It never sends. Drafts appear on the dashboard and in
$DATA_DIR/outbox/ for you to read, edit and send yourself: a rental enquiry is
an application, and the portals' terms forbid automated messaging.

The text is filled from the "applicant" block in settings. Blank fields are
left out rather than printed empty.
"""
import os, re, datetime
import config

OUTBOX = os.path.join(config.DATA_DIR, "outbox")


def _a():
    return config.APPLICANT


def _age():
    born = _a().get("born") or ""
    try:
        b = datetime.datetime.strptime(born, "%d.%m.%Y").date()
    except ValueError:
        return None
    t = datetime.date.today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


def _docs_line_de():
    A = _a()
    docs = ["die letzten Gehaltsabrechnungen", "Ausweis bzw. Reisepass"]
    if A.get("has_arbeitgeberbestaetigung"):
        docs.insert(0, "eine Arbeitgeberbestätigung für Wohnzwecke")
    if A.get("has_anmeldung"):
        docs.append("Meldebescheinigung")
    if A.get("has_schufa"):
        docs.append("SCHUFA-Auskunft")
        tail = "kann ich Ihnen sofort zusenden"
    else:
        tail = ("kann ich Ihnen sofort zusenden; eine SCHUFA-Auskunft reiche ich "
                "innerhalb weniger Tage nach")
    return ", ".join(docs[:-1]) + " und " + docs[-1] + " " + tail


def _household_de():
    A = _a()
    n = int(A.get("household") or 1)
    who = "allein" if n == 1 else f"mit {n} Personen"
    parts = [f"Ich würde die Wohnung {who} bewohnen"]
    parts.append("bin Raucher" if A.get("smoker") else "bin Nichtraucher")
    parts.append("habe ein Haustier" if A.get("pets") else "habe keine Haustiere")
    return ", ".join(parts[:-1]) + " und " + parts[-1] + "."


def _household_en():
    A = _a()
    n = int(A.get("household") or 1)
    who = "alone" if n == 1 else f"as a household of {n}"
    smoke = "I smoke" if A.get("smoker") else "I do not smoke"
    pets = "I have a pet" if A.get("pets") else "I have no pets"
    return f"I would live in the apartment {who}, {smoke} and {pets}."


def _sig():
    A = _a()
    return "\n".join(x for x in (A.get("name"), A.get("phone"), A.get("email")) if x)


def draft_de(rec):
    A = _a()
    where = rec.get("area") or rec.get("plz") or "München"
    about = []
    if A.get("name"):
        age = _age()
        about.append(f"Ich heiße {A['name']}" + (f", bin {age} Jahre alt" if age else ""))
    if A.get("job") and A.get("employer"):
        since = f"seit {A['since']} " if A.get("since") else ""
        about.append(f"arbeite {since}als {A['job']} bei {A['employer']}")
    intro = ("Kurz zu mir: " + " und ".join(about) + ". ") if about else ""
    money = ""
    if A.get("contract"):
        money += f"Mein Arbeitsvertrag ist {A['contract']}"
        if A.get("gross_year"):
            money += f", mein Bruttogehalt liegt bei {A['gross_year']}"
            if A.get("gross_month"):
                money += f" (ca. {A['gross_month']} brutto monatlich)"
        money += ". "
    move = (f"Mein Wunschtermin für den Einzug ist der {A['move_in']}, und ich suche "
            if A.get("move_in") else "Ich suche ")
    return (
        f"Guten Tag,\n\n"
        f"ich interessiere mich sehr für Ihre Wohnung in {where} und würde sie gerne besichtigen.\n\n"
        f"{intro}{money}{_household_de()}\n\n"
        f"{move}ausdrücklich ein unbefristetes Mietverhältnis. "
        f"Alle üblichen Unterlagen – {_docs_line_de()}.\n\n"
        f"Für eine Besichtigung bin ich zeitlich sehr flexibel, auch abends oder am Wochenende. "
        f"Über eine Rückmeldung würde ich mich sehr freuen.\n\n"
        f"Mit freundlichen Grüßen\n{_sig()}"
    ).rstrip()


def draft_en(rec):
    A = _a()
    where = rec.get("area") or rec.get("plz") or "Munich"
    about = []
    if A.get("name"):
        age = _age()
        about.append(f"my name is {A['name']}" + (f", I am {age}" if age else ""))
    if A.get("job") and A.get("employer"):
        since = f" since {A['since']}" if A.get("since") else ""
        perm = " on a permanent contract" if (A.get("contract") or "").lower() == "unbefristet" else ""
        about.append(f"I have been working as a {A['job']} at {A['employer']}{since}{perm}")
    intro = ("A little about me: " + ", and ".join(about) + ". ") if about else ""
    money = f"My gross salary is {A['gross_year']}. " if A.get("gross_year") else ""
    move = (f"I am looking to move in on {A['move_in']} and specifically want "
            if A.get("move_in") else "I am specifically looking for ")
    schufa = "," if A.get("has_schufa") else ", with a SCHUFA credit report to follow within a few days,"
    return (
        f"Hello,\n\n"
        f"I am very interested in your apartment in {where} and would like to arrange a viewing.\n\n"
        f"{intro}{money}{_household_en()}\n\n"
        f"{move}an open-ended tenancy. I can provide payslips, passport and "
        f"registration certificate immediately{schufa} along with anything else you need.\n\n"
        f"I am very flexible for a viewing, including evenings and weekends. "
        f"I look forward to hearing from you.\n\nBest regards\n{_sig()}"
    ).rstrip()


def write_draft(rec):
    """Write a draft to outbox/ and return its path."""
    os.makedirs(OUTBOX, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", (rec.get("title") or "listing").lower())[:48].strip("-")
    path = os.path.join(OUTBOX, f"{rec['uid'].replace(':', '_')}_{slug}.md")
    if os.path.exists(path):
        return path
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {rec.get('title','(no title)')}\n\n")
        f.write(f"- **Listing:** {rec.get('url','')}\n")
        f.write(f"- **Rent:** {rec.get('price')} EUR   **Size:** {rec.get('sqm')} m2   "
                f"**Area:** {rec.get('area')} (~{rec.get('commute')} min)\n")
        f.write(f"- **Score:** {rec.get('score')}  ({rec.get('verdict')})\n")
        f.write(f"- **Why:** {rec.get('reasons','')}\n\n")
        f.write("**Not sent.** Read it, fix anything wrong, then send it yourself "
                "from the listing page.\n\n---\n\n## German\n\n```\n")
        f.write(draft_de(rec))
        f.write("\n```\n\n## English\n\n```\n")
        f.write(draft_en(rec))
        f.write("\n```\n")
    return path
