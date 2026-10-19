#!/usr/bin/env python3
"""Re-run the matcher over every stored listing. The dashboard runs this after
every settings change.

Listings already reported keep reported=1 so you are not spammed twice; a
listing that newly becomes a HIT is set back to unreported so it surfaces.
"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import store, match, scam

def main():
    c = store.conn()
    rows = c.execute("SELECT * FROM listings").fetchall()
    changed = 0
    for r in rows:
        rec = dict(r)
        legacy = r["avail"] is None
        rec["avail"] = r["avail"] or ""
        # 'loc' is not a column; rebuild it so PLZ/commute detection still works
        rec["loc"] = f"{r['plz'] or ''} {r['area'] or ''}".strip()
        score, verdict, reasons = match.evaluate(rec)

        # Re-apply scam screening too. Without this, a rescore resurrects
        # listings that scan.py had already killed as scams/junk.
        risk, flags = scam.assess(rec, rec.get("body") or "")
        if scam.verdict(risk) == "SCAM":
            score, verdict = 0, "REJECT"
            reasons = [f"scam risk {risk}: " + "; ".join(flags)]
        elif flags:
            reasons.append("caution -- " + "; ".join(flags))
            if scam.verdict(risk) == "SUSPECT" and verdict == "HIT":
                verdict = "MAYBE"       # dashboard only, never pushed

        # Rows stored before avail/warm were kept lack facts the original verdict
        # used (a "frei bis" date, the warm rent, the full description), so they
        # would wrongly pass. They may be demoted, never revived.
        if legacy and r["verdict"] == "REJECT" and verdict != "REJECT":
            continue

        # A listing that vanished from the portal stays gone, whatever it scores now.
        if r["verdict"] == "GONE" and verdict != "REJECT":
            verdict = "GONE"

        if score != r["score"] or verdict != r["verdict"]:
            changed += 1
            newly_good = verdict in ("HIT", "MAYBE") and r["verdict"] == "REJECT"
            c.execute("UPDATE listings SET score=?, verdict=?, reasons=?"
                      + (", reported=0" if newly_good else "") + " WHERE uid=?",
                      (score, verdict, " ; ".join(reasons), r["uid"]))
    c.commit()
    counts = {row["verdict"]: row["n"] for row in
              c.execute("SELECT verdict, COUNT(*) n FROM listings GROUP BY verdict")}
    c.close()
    print(f"rescored {len(rows)} listings, {changed} changed -> {counts}")

if __name__ == "__main__":
    main()
