import React, { useEffect, useState } from "react";
import { api, ago } from "./api.js";

export default function Activity({ status }) {
  const [runs, setRuns] = useState([]);

  useEffect(() => {
    const load = () => api.runs().then(setRuns);
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, []);

  const jobs = Object.entries(status?.last_jobs || {});
  return (
    <div>
      {jobs.length > 0 && (
        <section className="panel">
          <h2>Since the dashboard started</h2>
          {jobs.map(([job, j]) => (
            <div key={job} className="job">
              <b>{job}</b> <span className={j.ok ? "ok" : "bad"}>{j.ok ? "ok" : "failed"}</span>{" "}
              <span className="muted small">{ago(j.at)}</span>
              {j.output && <pre>{j.output}</pre>}
            </div>
          ))}
        </section>
      )}

      <section className="panel">
        <h2>Run log</h2>
        <p className="muted small">
          One row per source per scan. A source that keeps returning 0 is broken or blocked, not a quiet market.
        </p>
        <div className="scroll">
          <table className="runs">
            <thead>
              <tr><th>When</th><th>Source</th><th>Fetched</th><th>New</th><th>Matched</th><th>Note</th></tr>
            </thead>
            <tbody>
              {runs.map((r, i) => {
                const bad = /^(ERROR|WARNING|ABORTED|ALERT)/.test(r.note || "");
                return (
                  <tr key={i} className={bad ? "bad-row" : ""}>
                    <td title={r.ts}>{r.ts?.replace("T", " ").slice(0, 16)}</td>
                    <td>{r.source}</td>
                    <td>{r.fetched}</td>
                    <td>{r.new}</td>
                    <td>{r.matched}</td>
                    <td className="note">{r.note}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
