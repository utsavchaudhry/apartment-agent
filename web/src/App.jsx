import React, { useEffect, useState, useCallback } from "react";
import { api, ago } from "./api.js";
import Listings from "./Listings.jsx";
import Settings from "./Settings.jsx";
import Activity from "./Activity.jsx";

const TABS = [
  ["listings", "Listings"],
  ["settings", "Settings"],
  ["activity", "Activity"],
];

export default function App() {
  const [tab, setTab] = useState(() => location.hash.slice(1) || "listings");
  const [status, setStatus] = useState(null);
  const [err, setErr] = useState("");

  const refresh = useCallback(() => {
    api.status().then(setStatus).catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    location.hash = tab;
  }, [tab]);

  async function scanNow() {
    setErr("");
    try {
      await api.scan();
      setTimeout(refresh, 500);
    } catch (e) {
      setErr(e.message);
    }
  }

  const c = status?.counts || {};
  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo">🏠</span>
          <div>
            <h1>Apartment Agent</h1>
            <p className="muted small">
              {status ? (
                <>
                  last fetch {ago(status.last_successful_fetch)} ·{" "}
                  {status.running ? (
                    <b className="pulse">{status.running} running…</b>
                  ) : (
                    <>next scan {ago(status.next_scan)}</>
                  )}
                </>
              ) : (
                "connecting…"
              )}
            </p>
          </div>
        </div>
        <button className="btn primary" onClick={scanNow} disabled={!!status?.running}>
          {status?.running ? "Scanning…" : "Scan now"}
        </button>
      </header>

      {status && (
        <section className="stats">
          <Stat label="Matches" value={(c.HIT || 0) + (c.MAYBE || 0)} accent />
          <Stat label="Contacted" value={status.contacted} />
          <Stat label="New in 24 h" value={status.last_24h.new} />
          <Stat label="Seen in total" value={Object.values(c).reduce((a, b) => a + b, 0)} />
        </section>
      )}

      {err && <div className="banner error">{err}</div>}

      <nav className="tabs">
        {TABS.map(([k, label]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </nav>

      <main>
        {tab === "listings" && <Listings onChange={refresh} />}
        {tab === "settings" && <Settings />}
        {tab === "activity" && <Activity status={status} />}
      </main>
    </div>
  );
}

function Stat({ label, value, accent }) {
  return (
    <div className={"stat" + (accent ? " accent" : "")}>
      <div className="num">{value ?? "–"}</div>
      <div className="muted small">{label}</div>
    </div>
  );
}
