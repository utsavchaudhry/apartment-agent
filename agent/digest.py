#!/usr/bin/env python3
"""Nightly digest. Deterministic, zero tokens.

Writes $DATA_DIR/digests/YYYY-MM-DD.md, drafts an enquiry per new match and
marks them reported. Pushes an alert if nothing at all was fetched in 24h, so a
blocked source cannot pass for a quiet market.
"""
import sys, os, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config, store, contact, notify as alerts

DIGESTS = os.path.join(config.DATA_DIR, "digests")


def main():
    always = "--always" in sys.argv
    c = store.conn()
    hits = [dict(r) for r in store.unreported_hits(c)]

    today = datetime.date.today()
    since = (datetime.datetime.now() - datetime.timedelta(hours=24)).isoformat(timespec="seconds")
    scanned = c.execute("SELECT COALESCE(SUM(fetched),0) f, COALESCE(SUM(new),0) n "
                        "FROM runs WHERE ts > ?", (since,)).fetchone()
    errs = c.execute(
        "SELECT source, note FROM runs WHERE ts > ? AND note != '' "
        "AND (note LIKE 'ERROR%' OR note LIKE 'WARNING%' OR note LIKE 'ABORTED%')",
        (since,)).fetchall()

    # A broken agent must never look like a quiet market. If nothing was
    # fetched at all in 24h, that is a fault and it gets pushed, not buried.
    if scanned["f"] == 0:
        alerts.push("Apartment agent is not fetching",
                    f"No ads fetched in 24h across {len(errs)} failed runs. "
                    f"Check the Activity tab on the dashboard.", priority="high")
        store.log_run(c, "digest", 0, 0, 0, "ALERT: zero fetched in 24h")
        c.commit(); c.close()
        print(f"{today}: FAULT — nothing fetched in 24h. Sources may be blocked.")
        return

    if not hits and not always:
        store.log_run(c, "digest", 0, 0, 0, "quiet day")
        c.commit(); c.close()
        print(f"{today}: nothing new worth reporting "
              f"({scanned['n']} new ads seen, none matched).")
        return

    os.makedirs(DIGESTS, exist_ok=True)
    path = os.path.join(DIGESTS, f"{today}.md")
    lines = [f"# Apartment digest — {today:%A %d %B %Y}", ""]
    lines.append(f"Scanned **{scanned['f']}** ads in the last 24h, **{scanned['n']}** of them new. "
                 f"**{len(hits)}** worth your attention.")
    lines.append("")

    if errs:
        lines.append("> Source problems: " + "; ".join(f"{e['source']}" for e in errs))
        lines.append("")

    for i, h in enumerate(hits, 1):
        drafted = contact.write_draft(h)
        lines += [
            f"## {i}. {h['title']}",
            "",
            f"| | |",
            f"|---|---|",
            f"| **Rent** | {h['price']} € |",
            f"| **Size** | {h['sqm'] or '?'} m² · {h['rooms'] or '?'} rooms |",
            f"| **Area** | {h['area'] or '?'} — ~{h['commute'] or '?'} min commute |",
            f"| **Move-in** | {h['move_in'] or 'not stated — check the ad'} |",
            f"| **Score** | {h['score']}/100 ({h['verdict']}) |",
            f"| **Source** | {h['source']} |",
            "",
            f"{h['reasons']}",
            "",
            f"- Listing: {h['url']}",
            f"- Draft enquiry (not sent): `outbox/{os.path.basename(drafted)}`",
            "",
        ]

    lines += ["---", "",
              "Drafts are **not sent**. Open one, check it reads the way you want, "
              "then send it from the listing page yourself."]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    c.executemany("UPDATE listings SET drafted=1 WHERE uid=?", [(h["uid"],) for h in hits])
    store.mark_reported(c, [h["uid"] for h in hits])
    store.log_run(c, "digest", scanned["f"], scanned["n"], len(hits), f"wrote {path}")
    c.commit(); c.close()

    print(f"{today}: {len(hits)} match(es) -> {path}")


if __name__ == "__main__":
    main()
