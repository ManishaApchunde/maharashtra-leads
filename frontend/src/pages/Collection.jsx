import { useState } from "react";
import DistrictCollector from "../components/DistrictCollector";
import GeoFilter from "../components/GeoFilter";
import { ErrorBox, Panel, Stat } from "../components/ui";
import { useApi, useMeta } from "../hooks/useApi";
import { api } from "../services/api";

export default function Collection() {
  const { meta, categories, sources } = useMeta();
  const status = useApi("/collection/status");
  const [geo, setGeo] = useState({ district: "", taluka: "", city: "" });
  const [keyword, setKeyword] = useState("Xerox shop");
  const [category, setCategory] = useState("Xerox");
  const [pages, setPages] = useState(1);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [runFilter, setRunFilter] = useState({ district: "", source: "" });
  const runs = useApi("/collection/runs", { district: runFilter.district, page_size: 50 });

  async function run() {
    setBusy(true); setError(null); setResult(null);
    try {
      setResult(await api.post("/collection/run", { ...geo, keyword, category: category || null, max_pages: Number(pages) }));
      runs.reload();
    } catch (e) { setError(e); runs.reload(); } finally { setBusy(false); }
  }

  const configured = status.data?.google_places_configured;
  const items = (runs.data?.items || []).filter((r) => !runFilter.source || r.source === runFilter.source);

  return (
    <>
      <div className="page-head"><div><h1>Data collection</h1>
        <p className="muted">Collect area by area, keyword by keyword. Only official APIs and permitted sources – no page scraping.</p></div></div>

      {!configured && (
        <div className="notice warn">GOOGLE_PLACES_API_KEYS is not set in backend/.env, so API collection is off.
          You can still collect data from CSV/Excel files on the Import page.</div>
      )}
      <Panel title="Collect a whole district automatically">
        <p className="muted small" style={{ marginTop: 0 }}>Select a district and start. Every taluka, every village/town
          and every ticked keyword is searched one after another in the background — you can leave this page and come back.</p>
        <DistrictCollector configured={configured} allKeywords={meta.search_keywords} onProgress={runs.reload} />
        <div className="notice small">Google's terms limit how long most Places data may be stored. Check the current
          Google Maps Platform terms before keeping these rows in a long-term marketing list.</div>
      </Panel>

      <Panel title="Single search (one area, one keyword)">
        <GeoFilter value={geo} onChange={setGeo} showArea={false} />
        <div className="filter-row">
          <label><span>Keyword</span>
            <select value={keyword} onChange={(e) => setKeyword(e.target.value)}>
              {meta.search_keywords.map((k) => <option key={k}>{k}</option>)}
            </select></label>
          <label><span>Category to tag</span>
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">(detect from name)</option>{categories.map((c) => <option key={c}>{c}</option>)}
            </select></label>
          <label><span>Pages (20 results each)</span>
            <select value={pages} onChange={(e) => setPages(e.target.value)}><option>1</option><option>2</option><option>3</option></select></label>
        </div>
        <button className="primary" disabled={!configured || !geo.district || busy} onClick={run}>
          {busy ? "Searching…" : "Run search"}</button>
        <ErrorBox error={error} />
        {result && (
          <>
            <p><strong>Search area:</strong> {result.search_area} · <strong>Keyword:</strong> {result.keyword}</p>
            <div className="stats">
              <Stat label="Results" value={result.total_results} />
              <Stat label="New businesses" value={result.new_count} tone="good" />
              <Stat label="Duplicates" value={result.duplicate_count + result.possible_duplicate_count} tone="warn" />
              <Stat label="Invalid" value={result.invalid_count} tone="bad" />
            </div>
          </>
        )}
      </Panel>

      <Panel title="Collection log" actions={
        <div className="row-gap">
          <select value={runFilter.district} onChange={(e) => setRunFilter({ ...runFilter, district: e.target.value })}>
            <option value="">All districts</option>
            {[...new Set((runs.data?.items || []).map((r) => r.district).filter(Boolean))].map((d) => <option key={d}>{d}</option>)}
          </select>
          <select value={runFilter.source} onChange={(e) => setRunFilter({ ...runFilter, source: e.target.value })}>
            <option value="">All sources</option>{sources.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>}>
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>When</th><th>Type</th><th>Search area / file</th><th>Keyword</th><th>Category</th><th>Source</th>
              <th className="num">Results</th><th className="num">New</th><th className="num">Dup</th><th className="num">Possible</th><th className="num">Invalid</th><th>Status</th></tr></thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id}>
                  <td className="small">{new Date(r.created_at).toLocaleString("en-IN")}</td>
                  <td>{r.run_type}</td>
                  <td>{r.search_area || r.file_name}</td><td>{r.keyword}</td><td>{r.category}</td><td className="small">{r.source}</td>
                  <td className="num">{r.total_results}</td><td className="num">{r.new_count}</td><td className="num">{r.duplicate_count}</td>
                  <td className="num">{r.possible_duplicate_count}</td><td className="num">{r.invalid_count}</td>
                  <td title={r.message || ""}>{r.status}</td>
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={12} className="muted center">No collection runs yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
