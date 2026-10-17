#!/usr/bin/env python3
"""One scan pass. Started by the scheduler in server.py. No LLM, no browser, no tokens.

Fetches each working portal, scores every ad it has never seen before, and
writes the survivors to SQLite. Output is a couple of lines to the log.
"""
import sys, os, re, traceback, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config, sources, store, match, notify, scam


def main():
    c = store.conn()

    # Right after boot the network may not be up yet. Without this wait every
    # fetch fails and the run looks like a quiet market.
    if not sources.wait_for_network():
        store.log_run(c, "scan", 0, 0, 0, "ABORTED: no network after 180s")
        c.commit(); c.close()
        print(f"{datetime.datetime.now():%Y-%m-%d %H:%M}  aborted -- no network")
        return

    totals = dict(fetched=0, new=0, hit=0, maybe=0)
    fresh_hits = []

    for name, fn in sources.enabled():
        try:
            rows = fn(max_price=config.MAX_RENT_WARM)
        except Exception:
            store.log_run(c, name, 0, 0, 0, "ERROR " + traceback.format_exc(limit=1).strip())
            c.commit()
            continue

        new = hit = maybe = 0
        now_iso = datetime.datetime.now().isoformat(timespec="seconds")
        for r in rows:
            if not r.get("uid"):
                continue
            # Touch every uid we saw, new or not -- this is how we detect the
            # ones that quietly disappear (3 of 9 died within 24h on 21.09).
            c.execute("UPDATE listings SET last_seen=? WHERE uid=?", (now_iso, r["uid"]))
            if store.seen(c, r["uid"]):
                continue
            new += 1
            score, verdict, reasons = match.evaluate(r)

            plz = ""
            m = re.search(r"\b(\d{5})\b", f"{r.get('loc','')} {r.get('title','')}")
            if m:
                plz = m.group(1)
            area, commute = config.PLZ_COMMUTE.get(plz, ("", None))
            _, mdate, _ = match.move_in_verdict(r)

            # Teasers omit the move-in date, so anything that survives the
            # cheap filters gets its actual ad page read before we trust it.
            # Keep whatever the source already told us (ImmoScout reports a
            # relative age); the detail fetch may refine it but must not erase it.
            full_text, posted, checked = "", r.get("posted", "") or "", 0
            if verdict in ("HIT", "MAYBE"):
                d = sources.detail(r.get("url", ""))
                if d:
                    checked = 1
                    full_text = d.get("text", "")
                    posted = d.get("posted", "")
                    r = dict(r)
                    r["avail"] = d.get("avail") or r.get("avail", "")
                    if d.get("warm"):
                        r["warm"] = d["warm"]
                    r["posted"] = posted
                    r["body"] = (r.get("body", "") + " | " + full_text)[:4000]
                    score, verdict, reasons = match.evaluate(r)
                    _, mdate, _ = match.move_in_verdict(r)

            risk, flags = scam.assess(r, full_text)
            if scam.verdict(risk) == "SCAM":
                verdict, score = "REJECT", 0
                reasons = [f"scam risk {risk}: " + "; ".join(flags)]
            elif flags:
                reasons.append("caution -- " + "; ".join(flags))

            rec = dict(
                uid=r["uid"], source=r["source"], url=r.get("url", ""),
                title=r.get("title", ""), price=int(r["price"]) if r.get("price") else None,
                sqm=r.get("sqm"), rooms=r.get("rooms"), plz=plz, area=area,
                commute=commute, move_in=str(mdate) if mdate else "",
                score=score, verdict=verdict, reasons=" ; ".join(reasons),
                body=(r.get("body") or "")[:4000],
                avail=r.get("avail") or "", warm=r.get("warm"),
                posted=posted, scam_risk=risk, scam_flags="; ".join(flags),
                checked=checked,
            )
            store.add(c, rec)
            # Count the FINAL verdict, after the ad page and scam check.
            if verdict == "HIT":
                hit += 1
                # A good flat in Munich is gone in hours, so alert now rather
                # than waiting for the evening digest.
                fresh_hits.append(rec)
            elif verdict == "MAYBE":
                maybe += 1

        # A source that returns nothing is a fault, not a quiet market. Say so,
        # so a silent breakage cannot masquerade as "no new listings today".
        note = "" if rows else "WARNING: source returned 0 rows"
        store.log_run(c, name, len(rows), new, hit + maybe, note)
        c.commit()
        totals["fetched"] += len(rows); totals["new"] += new
        totals["hit"] += hit; totals["maybe"] += maybe

    # Sweep: a candidate that has not appeared in any scan for 24h is gone.
    cutoff = (datetime.datetime.now() - datetime.timedelta(hours=24)).isoformat(timespec="seconds")
    gone = c.execute(
        "UPDATE listings SET verdict='GONE' WHERE verdict IN ('HIT','MAYBE') "
        "AND last_seen IS NOT NULL AND last_seen < ?", (cutoff,)).rowcount
    if gone:
        store.log_run(c, "sweep", 0, 0, 0, f"{gone} listing(s) vanished -> GONE")
    c.commit(); c.close()

    cap = int(getattr(config, "MAX_ALERTS_PER_SCAN", 5))
    for rec in fresh_hits[:cap]:        # cap, so a portal glitch cannot spam you
        notify.announce(rec)

    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M}  "
          f"fetched={totals['fetched']} new={totals['new']} "
          f"HIT={totals['hit']} MAYBE={totals['maybe']}"
          + (f" alerted={len(fresh_hits[:cap])}" if fresh_hits else ""))


if __name__ == "__main__":
    main()
