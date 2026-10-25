import { useEffect, useRef, useState } from "react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { ErrorBox, Stat } from "./ui";

// A shorter set that still covers every business type (several of the 19 keywords are near-synonyms).
const CORE_KEYWORDS = ["Xerox", "photocopy", "printing shop", "digital printing", "cyber cafe", "CSC",
  "DTP centre", "online services", "e seva", "document center"];
const ALL = "__all__";

/**
 * Pick a district -> loops every taluka, every known village/town and every keyword automatically.
 * Runs on the server in the background; this panel polls its progress.
 */
export default function DistrictCollector({ configured, allKeywords, onProgress }) {
  const districts = useApi("/districts");
  const [district, setDistrict] = useState("");
  const [keywords, setKeywords] = useState([]);
  const [opts, setOpts] = useState({
    taluka_pages: 3, village_pages: 1, include_villages: true, include_city_areas: true,
    grid_sweep: false, grid_km: 5, skip_done: true,
  });
  const [plan, setPlan] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [starting, setStarting] = useState(false);
  const lastDone = useRef(0);

  // Default: every keyword ticked, so nothing has to be picked by hand.
  useEffect(() => { if (allKeywords.length && !keywords.length) setKeywords(allKeywords); }, [allKeywords]); // eslint-disable-line

  const body = () => ({
    district: district === ALL ? null : district, all_districts: district === ALL, keywords, ...opts,
    grid_km: Number(opts.grid_km), taluka_pages: Number(opts.taluka_pages), village_pages: Number(opts.village_pages),
  });

  // Estimate before starting
  useEffect(() => {
    if (!district || !keywords.length) { setPlan(null); return; }
    const t = setTimeout(() => api.post("/collection/district-plan", body()).then(setPlan).catch(() => setPlan(null)), 300);
    return () => clearTimeout(t);
  }, [district, keywords, opts]); // eslint-disable-line

  // Pick up a job that is already running (e.g. after a page refresh) and poll it while it runs.
  useEffect(() => { api.get("/collection/district-jobs").then((r) => r.active && setJob(r.active)).catch(() => {}); }, []);
  const running = job && (job.status === "running" || job.status === "queued");
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => {
      api.get(`/collection/district-jobs/${job.id}`).then((j) => {
        setJob(j);
        if (j.done_steps - lastDone.current >= 10 || j.status !== "running") { lastDone.current = j.done_steps; onProgress?.(); }
      }).catch(() => {});
    }, 2000);
    return () => clearInterval(t);
  }, [running, job?.id]); // eslint-disable-line

  async function start() {
    setError(null); setStarting(true);
    try { lastDone.current = 0; setJob(await api.post("/collection/district-jobs", body())); }
    catch (e) { setError(e); } finally { setStarting(false); }
  }
  async function stop() {
    try { setJob(await api.post(`/collection/district-jobs/${job.id}/cancel`)); } catch (e) { setError(e); }
  }

  const toggle = (k) => setKeywords((ks) => ks.includes(k) ? ks.filter((x) => x !== k) : [...ks, k]);
  const set = (patch) => setOpts((o) => ({ ...o, ...patch }));
  const pct = job?.total_steps ? Math.min(100, Math.round((job.done_steps / job.total_steps) * 100)) : 0;
  const p = plan?.districts?.[0];

  return (
    <>
      <div className="filter-row">
        <label><span>District</span>
          <select value={district} onChange={(e) => setDistrict(e.target.value)} disabled={running}>
            <option value="">Select a district…</option>
            <option value={ALL}>★ All 36 districts (one after another)</option>
            {(districts.data || []).map((d) => <option key={d.id} value={d.name}>{d.name}{d.business_count ? ` (${d.business_count})` : ""}</option>)}
          </select></label>
        <label><span>Pages per taluka (20 results each)</span>
          <select value={opts.taluka_pages} onChange={(e) => set({ taluka_pages: e.target.value })} disabled={running}>
            <option>1</option><option>2</option><option>3</option></select></label>
        <label><span>Pages per village / town</span>
          <select value={opts.village_pages} onChange={(e) => set({ village_pages: e.target.value })} disabled={running}>
            <option>1</option><option>2</option><option>3</option></select></label>
      </div>

      <div className="kw-head">
        <span className="muted small">Keywords searched in every area ({keywords.length}/{allKeywords.length})</span>
        <button className="link" disabled={running} onClick={() => setKeywords(allKeywords)}>All</button>
        <button className="link" disabled={running} onClick={() => setKeywords(allKeywords.filter((k) => CORE_KEYWORDS.includes(k)))}>Core 10</button>
        <button className="link" disabled={running} onClick={() => setKeywords([])}>None</button>
      </div>
      <div className="kw-grid">
        {allKeywords.map((k) => (
          <label key={k} className={`chip ${keywords.includes(k) ? "on" : ""}`}>
            <input type="checkbox" checked={keywords.includes(k)} onChange={() => toggle(k)} disabled={running} />{k}
          </label>
        ))}
      </div>

      <div className="row-gap opts">
        <label className="check"><input type="checkbox" checked={opts.include_villages} disabled={running}
          onChange={(e) => set({ include_villages: e.target.checked })} />Every village / town in the database</label>
        <label className="check"><input type="checkbox" checked={opts.include_city_areas} disabled={running}
          onChange={(e) => set({ include_city_areas: e.target.checked })} />Big-city areas (Pune, Mumbai, Thane, Nagpur…)</label>
        <label className="check"><input type="checkbox" checked={opts.skip_done} disabled={running}
          onChange={(e) => set({ skip_done: e.target.checked })} />Skip areas already searched (resume)</label>
        <label className="check"><input type="checkbox" checked={opts.grid_sweep} disabled={running}
          onChange={(e) => set({ grid_sweep: e.target.checked })} />Map-grid sweep (finds villages not in the database)</label>
        {opts.grid_sweep && (
          <select value={opts.grid_km} onChange={(e) => set({ grid_km: e.target.value })} disabled={running}>
            <option value="3">3 km cells</option><option value="5">5 km cells</option>
            <option value="8">8 km cells</option><option value="12">12 km cells</option>
          </select>
        )}
      </div>

      {plan && !running && (
        <div className="notice small">
          {district === ALL
            ? <>All 36 districts: <strong>{plan.searches.toLocaleString("en-IN")}</strong> searches</>
            : <><strong>{p.talukas}</strong> talukas{p.city_areas ? <> + <strong>{p.city_areas}</strong> city areas</> : null}
              {opts.include_villages && <> + <strong>{p.known_villages}</strong> villages/towns known now</>} ×{" "}
              <strong>{plan.keywords}</strong> keywords = <strong>{plan.searches.toLocaleString("en-IN")}</strong> searches</>}
          , up to <strong>{plan.max_requests.toLocaleString("en-IN")}</strong> Google API requests (fewer when an area has under 20 results).
          {" "}Villages discovered during the run are added automatically.
          {opts.grid_sweep && " Grid cells are added when the job reaches that step."}
          {" "}Each request is billed by Google — check your quota and the current Places API pricing.
        </div>
      )}

      {!running && (
        <button className="primary" disabled={!configured || !district || !keywords.length || starting} onClick={start}>
          {starting ? "Starting…" : district === ALL ? "Collect all of Maharashtra" : district ? `Collect all of ${district}` : "Collect whole district"}
        </button>
      )}
      <ErrorBox error={error} />

      {job && (
        <div className="job">
          <div className="job-head">
            <div>
              <strong>{job.status === "running" ? "Collecting" : job.status === "queued" ? "Starting" : job.status === "paused" ? "Paused (quota exhausted)" : job.status[0].toUpperCase() + job.status.slice(1)}</strong>
              {job.district && <> · {job.district}{job.district_count > 1 && ` (${job.district_index + 1}/${job.district_count})`}</>}
              {job.phase && <span className="muted"> · {job.phase.split(": ")[1]}</span>}
            </div>
            {running && <button onClick={stop}>Stop</button>}
          </div>
          <div className="progress"><div style={{ width: `${pct}%` }} /></div>
          <div className="muted small">
            {job.done_steps.toLocaleString("en-IN")} / {job.total_steps.toLocaleString("en-IN")} searches ({pct}%)
            {job.skipped_steps ? ` · ${job.skipped_steps} skipped (already done)` : ""}
            {job.failed_steps ? ` · ${job.failed_steps} failed` : ""} · {job.api_requests} API requests
            {running && " · total grows as new villages are found"}
          </div>
          {running && job.current && <div className="small job-current">Now: {job.current}</div>}
          <div className="stats">
            <Stat label="Results" value={job.totals.results} />
            <Stat label="New businesses" value={job.totals.new} tone="good" />
            <Stat label="Duplicates" value={job.totals.duplicates + job.totals.possible_duplicates} tone="warn" />
            <Stat label="Invalid" value={job.totals.invalid} tone="bad" />
          </div>
          {job.api_key?.configured > 0 && (
            <div className="muted small">
              API key: {job.api_key.active ? <>using <strong>#{job.api_key.active}</strong> of {job.api_key.configured}</> : <strong>all {job.api_key.configured} used up</strong>}
              {Object.keys(job.api_key.rejected || {}).length > 0 && (
                <> · done: {Object.entries(job.api_key.rejected).map(([i, k]) => `#${i} ${k === "quota_exhausted" ? "quota used" : "rejected"}`).join(", ")}</>
              )}
            </div>
          )}
          {job.district_count > 1 && job.per_district && (
            <div className="muted small">
              {["Completed", "Running", "Paused", "Failed", "Pending"].map((st) => {
                const n = Object.values(job.per_district).filter((d) => d.status === st).length;
                return n ? <span key={st}>{st}: {n} · </span> : null;
              })}districts
            </div>
          )}
          {job.error && <div className="error">⚠ {job.error}</div>}
          <details open={running}>
            <summary className="small">Activity log</summary>
            <pre className="joblog">{[...job.log].reverse().join("\n")}</pre>
          </details>
        </div>
      )}
    </>
  );
}
