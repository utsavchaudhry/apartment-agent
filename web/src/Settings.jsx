import React, { useEffect, useState } from "react";
import { api } from "./api.js";

// Immutable set at a dotted path: set(obj, "sources.wggesucht.pages", 3)
function setIn(obj, path, value) {
  const [k, ...rest] = path.split(".");
  return { ...obj, [k]: rest.length ? setIn(obj[k] || {}, rest.join("."), value) : value };
}
function getIn(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);
}

// The two lookup tables are edited as arrays of rows: as object keys, a postcode
// being typed would be re-sorted (JS orders numeric keys) and lose focus.
function toForm(d) {
  return {
    ...d,
    plz_commute: Object.entries(d.plz_commute || {}).map(([k, [label, min]]) => [k, label, min]),
    station_commute: Object.entries(d.station_commute || {}),
  };
}
function fromForm(f) {
  return {
    ...f,
    plz_commute: Object.fromEntries(
      f.plz_commute.filter((r) => String(r[0]).trim()).map(([k, label, min]) => [String(k).trim(), [label, min]])
    ),
    station_commute: Object.fromEntries(
      f.station_commute.filter((r) => String(r[0]).trim()).map(([k, v]) => [String(k).trim(), v])
    ),
  };
}

export default function Settings() {
  const [s, setS] = useState(null);
  const [saved, setSaved] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => {
    api.settings().then((d) => {
      setS(toForm(d));
      setSaved(toForm(d));
    });
  }, []);

  if (!s) return <p className="muted">Loading…</p>;

  const dirty = JSON.stringify(s) !== JSON.stringify(saved);
  const bind = (path) => ({ value: getIn(s, path), onChange: (v) => setS(setIn(s, path, v)) });

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      const d = toForm(await api.saveSettings(fromForm(s)));
      setS(d);
      setSaved(d);
      setMsg({ ok: true, text: "Saved. Stored listings are being re-graded against the new criteria." });
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setBusy(false);
    }
  }

  async function testPush() {
    setMsg(null);
    try {
      await api.testNotify();
      setMsg({ ok: true, text: "Test notification sent. Check your phone." });
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
  }

  async function resetAll() {
    if (!confirmReset) return setConfirmReset(true);
    const d = toForm(await api.defaults());
    // Keep the private ntfy topic and the applicant profile; reset the search.
    setS({ ...d, ntfy_topic: s.ntfy_topic, ntfy_token: s.ntfy_token, notify_email: s.notify_email, applicant: s.applicant });
    setConfirmReset(false);
    setMsg({ ok: true, text: "Defaults loaded. Press Save to apply them." });
  }

  return (
    <div className="settings">
      <Section title="Budget & size" hint="Rents are compared as warm rent (all-in). ImmoScout only reports cold rent, so running costs are estimated as base + per-m² × size.">
        <Num label="Max warm rent (€)" {...bind("max_rent_warm")} />
        <Num label="Bonus if under (€)" {...bind("prefer_under")} />
        <Num label="Min size (m²)" {...bind("min_sqm")} />
        <Num label="Ignore prices below (€)" hint="Placeholder prices like “1 € VB”" {...bind("min_plausible_rent")} />
        <Num label="Running costs base (€)" step="any" {...bind("nebenkosten_base")} />
        <Num label="Running costs per m² (€)" step="any" {...bind("nebenkosten_per_sqm")} />
      </Section>

      <Section title="Move-in window" hint="Leave empty for “from today, for the next six months”. Ads with a fixed end date are always rejected.">
        <Field label="Earliest move-in">
          <input type="date" value={s.move_in_earliest} onChange={(e) => setS(setIn(s, "move_in_earliest", e.target.value))} />
        </Field>
        <Field label="Latest move-in">
          <input type="date" value={s.move_in_latest} onChange={(e) => setS(setIn(s, "move_in_latest", e.target.value))} />
        </Field>
        <Num label="Ignore ads older than (days)" {...bind("stale_after_days")} />
      </Section>

      <Section title="Commute" hint="Door-to-door minutes to your office, per postcode. Postcodes not in this table are rejected. A station named in the ad text overrides the postcode estimate.">
        <Num label="Max commute (min)" {...bind("max_commute_min")} />
        <div className="full">
          <PlzTable value={s.plz_commute} onChange={(v) => setS(setIn(s, "plz_commute", v))} />
        </div>
        <div className="full">
          <StationTable value={s.station_commute} onChange={(v) => setS(setIn(s, "station_commute", v))} />
        </div>
        <Lines label="Words that count as “near a station”" {...bind("good_stations")} />
      </Section>

      <Section title="Filters" hint="One term per line. Matched as whole words, case-insensitive, umlauts folded (ü = ue).">
        <Lines label="Reject if anywhere in the ad" {...bind("block_terms")} rows={10} />
        <Lines label="Reject if in the title" {...bind("block_terms_title")} rows={10} />
        <Lines label="Minus 10 points" {...bind("soft_negative")} rows={4} />
      </Section>

      <Section title="Sources" hint="Where to search. IDs come from each portal's own search URL.">
        <Check label="Kleinanzeigen" {...bind("sources.kleinanzeigen.enabled")} />
        <Text label="Location slug" {...bind("sources.kleinanzeigen.location_slug")} />
        <Text label="Location id" hint="the l1234 part of the URL" {...bind("sources.kleinanzeigen.location_id")} />
        <Num label="Radius (km)" {...bind("sources.kleinanzeigen.radius_km")} />
        <hr className="full" />
        <Check label="WG-Gesucht (flats only)" {...bind("sources.wggesucht.enabled")} />
        <Text label="City slug" {...bind("sources.wggesucht.city_slug")} />
        <Num label="City id" {...bind("sources.wggesucht.city_id")} />
        <hr className="full" />
        <Check label="ImmoScout24" {...bind("sources.immoscout24.enabled")} />
        <Lines label="Regions (one path per line)" {...bind("sources.immoscout24.regions")} rows={5} />
      </Section>

      <Section title="Schedule" hint="Each scan makes roughly 10–20 requests, spaced a few seconds apart. Set night interval to 0 to pause overnight.">
        <Num label="Scan every (min), daytime" {...bind("schedule.interval_min")} />
        <Num label="Day starts (hour)" {...bind("schedule.day_start_hour")} />
        <Num label="Day ends (hour)" {...bind("schedule.day_end_hour")} />
        <Num label="Scan every (min), night" {...bind("schedule.night_interval_min")} />
        <Field label="Nightly digest at">
          <input type="time" value={s.schedule.digest_time} onChange={(e) => setS(setIn(s, "schedule.digest_time", e.target.value))} />
        </Field>
      </Section>

      <Section title="Phone notifications" hint="Free, via ntfy.sh. Install the ntfy app, tap +, and subscribe to the topic below. Anyone who knows the topic can read it, so keep it private.">
        <Text label="ntfy topic" {...bind("ntfy_topic")} />
        <Field label=" ">
          <div className="row">
            <a className="btn small" href={`https://ntfy.sh/${s.ntfy_topic}`} target="_blank" rel="noreferrer">Open topic</a>
            <button className="btn small" onClick={testPush} disabled={dirty} title={dirty ? "Save first" : ""}>Send test</button>
          </div>
        </Field>
        <Num label="Max alerts per scan" {...bind("max_alerts_per_scan")} />
        <Text label="ntfy token (optional)" hint="Only needed for e-mail forwarding" {...bind("ntfy_token")} />
        <Text label="Forward to e-mail (optional)" {...bind("notify_email")} />
      </Section>

      <Section title="Applicant" hint="Used only to fill in the draft enquiries. Stored on this machine, never sent anywhere by the agent. Blank fields are left out of the draft.">
        <Text label="Full name" {...bind("applicant.name")} />
        <Text label="Date of birth (DD.MM.YYYY)" {...bind("applicant.born")} />
        <Text label="Job title" {...bind("applicant.job")} />
        <Text label="Employer" {...bind("applicant.employer")} />
        <Text label="Employed since" {...bind("applicant.since")} />
        <Text label="Contract" hint="e.g. unbefristet" {...bind("applicant.contract")} />
        <Text label="Gross per year" {...bind("applicant.gross_year")} />
        <Text label="Gross per month" {...bind("applicant.gross_month")} />
        <Text label="Desired move-in" {...bind("applicant.move_in")} />
        <Num label="People in household" {...bind("applicant.household")} />
        <Text label="E-mail" {...bind("applicant.email")} />
        <Text label="Phone" {...bind("applicant.phone")} />
        <Check label="Smoker" {...bind("applicant.smoker")} />
        <Check label="Pets" {...bind("applicant.pets")} />
        <Check label="Have SCHUFA report" {...bind("applicant.has_schufa")} />
        <Check label="Have Anmeldung" {...bind("applicant.has_anmeldung")} />
        <Check label="Have employer confirmation" {...bind("applicant.has_arbeitgeberbestaetigung")} />
      </Section>

      <div className="savebar">
        {msg && <span className={msg.ok ? "ok" : "bad"}>{msg.text}</span>}
        <span className="grow" />
        <button className="btn ghost small" onClick={resetAll}>
          {confirmReset ? "Click again to reset search to defaults" : "Reset to defaults"}
        </button>
        <button className="btn ghost" onClick={() => setS(saved)} disabled={!dirty || busy}>Discard</button>
        <button className="btn primary" onClick={save} disabled={!dirty || busy}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}

function Section({ title, hint, children }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {hint && <p className="muted small">{hint}</p>}
      <div className="grid">{children}</div>
    </section>
  );
}

function Field({ label, hint, children, full }) {
  return (
    <label className={"field" + (full ? " full" : "")}>
      <span className="lbl">{label}</span>
      {children}
      {hint && <span className="muted small">{hint}</span>}
    </label>
  );
}

function Num({ label, hint, value, onChange, step }) {
  return (
    <Field label={label} hint={hint}>
      <input type="number" step={step || "1"} value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />
    </Field>
  );
}

function Text({ label, hint, value, onChange }) {
  return (
    <Field label={label} hint={hint}>
      <input type="text" value={value ?? ""} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

function Check({ label, value, onChange }) {
  return (
    <label className="check">
      <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

// Lists are edited as text so trailing blank lines survive typing; the server
// drops empty entries on save.
function Lines({ label, value, onChange, rows = 6 }) {
  return (
    <Field label={label} full>
      <textarea rows={rows} value={(value || []).join("\n")} onChange={(e) => onChange(e.target.value.split("\n"))} />
    </Field>
  );
}

function PlzTable({ value, onChange }) {
  const rows = value || [];
  const set = (i, col, v) => onChange(rows.map((r, j) => (j === i ? r.map((c, k) => (k === col ? v : c)) : r)));
  return (
    <div className="table-edit">
      <div className="lbl">Postcodes in range ({rows.length})</div>
      <div className="tbl">
        <div className="tr th"><span>PLZ</span><span>Area</span><span>Min</span><span /></div>
        {rows.map(([plz, label, min], i) => (
          <div className="tr" key={i}>
            <input value={plz} onChange={(e) => set(i, 0, e.target.value)} />
            <input value={label} onChange={(e) => set(i, 1, e.target.value)} />
            <input type="number" value={min} onChange={(e) => set(i, 2, Number(e.target.value))} />
            <button className="x" title="Remove" onClick={() => onChange(rows.filter((_, j) => j !== i))}>×</button>
          </div>
        ))}
      </div>
      <button className="btn small" onClick={() => onChange([...rows, ["", "", 30]])}>+ Add postcode</button>
    </div>
  );
}

function StationTable({ value, onChange }) {
  const rows = value || [];
  const set = (i, col, v) => onChange(rows.map((r, j) => (j === i ? r.map((c, k) => (k === col ? v : c)) : r)));
  return (
    <div className="table-edit">
      <div className="lbl">Stations named in the ad ({rows.length})</div>
      <div className="tbl two">
        <div className="tr th"><span>Text in ad</span><span>Min</span><span /></div>
        {rows.map(([k, v], i) => (
          <div className="tr" key={i}>
            <input value={k} onChange={(e) => set(i, 0, e.target.value)} />
            <input type="number" value={v} onChange={(e) => set(i, 1, Number(e.target.value))} />
            <button className="x" title="Remove" onClick={() => onChange(rows.filter((_, j) => j !== i))}>×</button>
          </div>
        ))}
      </div>
      <button className="btn small" onClick={() => onChange([...rows, ["", 30]])}>+ Add station</button>
    </div>
  );
}
