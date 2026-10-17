import React, { useEffect, useState } from "react";
import { api, ago } from "./api.js";

const VERDICTS = [
  ["HIT,MAYBE", "Matches"],
  ["HIT", "Hits"],
  ["MAYBE", "Maybe"],
  ["REJECT", "Rejected"],
  ["GONE", "Gone"],
  ["", "All"],
];
const STATUSES = [
  ["open", "Open"],
  ["contacted", "Contacted"],
  ["dismissed", "Dismissed"],
  ["", "Any status"],
];
const SORTS = [
  ["score", "Best score"],
  ["new", "Newest"],
  ["price", "Cheapest"],
  ["commute", "Shortest commute"],
];
const PAGE = 50;

export default function Listings({ onChange }) {
  const [verdict, setVerdict] = useState("HIT,MAYBE");
  const [status, setStatus] = useState("open");
  const [sort, setSort] = useState("score");
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [data, setData] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  function load(offset = 0) {
    setLoading(true);
    api
      .listings({ verdict, status, sort, q: qDebounced, limit: PAGE, offset })
      .then((d) =>
        setData((prev) => (offset ? { ...d, items: [...prev.items, ...d.items] } : d))
      )
      .finally(() => setLoading(false));
  }

  useEffect(() => load(0), [verdict, status, sort, qDebounced]);

  async function mark(uid, s) {
    await api.setStatus(uid, s);
    // Drop it from the view if it no longer matches the status filter.
    setData((d) => ({
      total: d.total,
      items: d.items
        .map((x) => (x.uid === uid ? { ...x, status: s } : x))
        .filter((x) => !status || (status === "open" ? !x.status : x.status === status)),
    }));
    onChange?.();
  }

  return (
    <div>
      <div className="filters">
        <div className="seg">
          {VERDICTS.map(([v, label]) => (
            <button key={label} className={verdict === v ? "on" : ""} onClick={() => setVerdict(v)}>
              {label}
            </button>
          ))}
        </div>
        <div className="row">
          <input
            className="search"
            placeholder="Search title, area, postcode…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map(([v, l]) => (
              <option key={l} value={v}>{l}</option>
            ))}
          </select>
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            {SORTS.map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </div>
      </div>

      <p className="muted small">{loading ? "Loading…" : `${data.total} listing(s)`}</p>

      {!loading && data.items.length === 0 && (
        <div className="empty">
          Nothing here yet. Scans run in the background; matches show up here and on your phone.
        </div>
      )}

      <div className="cards">
        {data.items.map((x) => (
          <Card key={x.uid} x={x} onMark={mark} />
        ))}
      </div>

      {data.items.length < data.total && (
        <button className="btn wide" onClick={() => load(data.items.length)} disabled={loading}>
          Load more
        </button>
      )}
    </div>
  );
}

function Card({ x, onMark }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [lang, setLang] = useState("de");
  const [copied, setCopied] = useState(false);

  function toggle() {
    if (!open && !detail) api.listing(x.uid).then(setDetail);
    setOpen(!open);
  }

  function copy() {
    const text = lang === "de" ? detail.draft_de : detail.draft_en;
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  const meta = [
    x.price != null && `${x.price} €`,
    x.sqm && `${Math.round(x.sqm)} m²`,
    x.rooms && `${x.rooms} Zi.`,
    x.area || x.plz,
    x.commute != null && `~${x.commute} min`,
    x.move_in && `from ${x.move_in}`,
  ].filter(Boolean);

  return (
    <article className={`card v-${x.verdict} ${x.status ? "s-" + x.status : ""}`}>
      <div className="card-head">
        <span className={`score v-${x.verdict}`} title={x.verdict}>{x.score}</span>
        <div className="grow">
          <a href={x.url} target="_blank" rel="noreferrer" className="title">
            {x.title || "(no title)"}
          </a>
          <div className="meta">{meta.join(" · ")}</div>
        </div>
      </div>
      <p className="reasons">{x.reasons}</p>
      {x.scam_risk >= 25 && <p className="warn">⚠ Scam risk {x.scam_risk}: {x.scam_flags}</p>}
      <div className="card-foot">
        <span className="muted small">
          {x.source} · seen {ago(x.first_seen)}
          {x.status && <span className={"tag " + x.status}>{x.status}</span>}
        </span>
        <div className="actions">
          <button className="btn small" onClick={toggle}>{open ? "Hide draft" : "Draft enquiry"}</button>
          {x.status !== "contacted" && (
            <button className="btn small" onClick={() => onMark(x.uid, "contacted")}>Contacted</button>
          )}
          {x.status !== "dismissed" && (
            <button className="btn small ghost" onClick={() => onMark(x.uid, "dismissed")}>Dismiss</button>
          )}
          {x.status && (
            <button className="btn small ghost" onClick={() => onMark(x.uid, "")}>Reopen</button>
          )}
        </div>
      </div>
      {open && (
        <div className="draft">
          {!detail ? (
            <p className="muted">Loading…</p>
          ) : (
            <>
              <div className="draft-bar">
                <div className="seg small">
                  <button className={lang === "de" ? "on" : ""} onClick={() => setLang("de")}>Deutsch</button>
                  <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>English</button>
                </div>
                <button className="btn small" onClick={copy}>{copied ? "Copied ✓" : "Copy"}</button>
              </div>
              <pre>{lang === "de" ? detail.draft_de : detail.draft_en}</pre>
              <p className="muted small">
                Not sent. Read it, adjust it, then send it from the listing page yourself. Fill in your
                profile under Settings → Applicant to personalise it.
              </p>
            </>
          )}
        </div>
      )}
    </article>
  );
}
