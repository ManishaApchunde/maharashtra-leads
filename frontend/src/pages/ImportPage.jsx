import { useEffect, useState } from "react";
import { ErrorBox, Panel, Stat } from "../components/ui";
import { useApi, useMeta } from "../hooks/useApi";
import { api } from "../services/api";

function Summary({ s }) {
  return (
    <div className="stats">
      <Stat label="Total rows" value={(s.total ?? s.total_results ?? 0).toLocaleString("en-IN")} />
      <Stat label="New" value={s.new ?? s.new_count} tone="good" />
      <Stat label="Duplicates (merged)" value={s.duplicates ?? s.duplicate_count} />
      <Stat label="Possible duplicates" value={s.possible_duplicates ?? s.possible_duplicate_count} tone="warn" />
      <Stat label="Invalid" value={s.invalid ?? s.invalid_count} tone="bad" />
    </div>
  );
}

export default function ImportPage() {
  const { meta, categories } = useMeta();
  const [file, setFile] = useState(null);
  const [source, setSource] = useState("CSV Import");
  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const runs = useApi("/collection/runs", { run_type: "csv", page_size: 15 });
  const reloadRuns = runs.reload;

  // Poll background imports
  useEffect(() => {
    if (result?.status !== "running") return;
    const t = setInterval(async () => {
      const r = await api.get(`/collection/runs/${result.run_id}`);
      if (r.status !== "running") { setResult({ ...result, ...r, errors: r.errors }); reloadRuns(); }
      else setResult((p) => ({ ...p, progress: r }));
    }, 3000);
    return () => clearInterval(t);
  }, [result, reloadRuns]);

  async function upload(e) {
    e.preventDefault();
    if (!file) return;
    setBusy(true); setError(null); setResult(null);
    const fd = new FormData();
    fd.append("file", file); fd.append("source", source);
    if (keyword) fd.append("keyword", keyword);
    if (category) fd.append("category", category);
    try { setResult(await api.upload("/import/csv", fd)); runs.reload(); }
    catch (err) { setError(err); } finally { setBusy(false); }
  }

  async function uploadSimple(path, f) {
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api.upload(path, fd); alert(JSON.stringify(r, null, 2)); } catch (err) { alert(err.message); }
  }

  return (
    <>
      <div className="page-head"><div><h1>Import</h1>
        <p className="muted">CSV or Excel (.xlsx). Every row is cleaned, phone-normalised and checked for duplicates.</p></div>
        <button onClick={() => api.download("/import/template")}>⬇ CSV template</button>
      </div>

      <Panel title="Upload businesses">
        <form className="form-grid" onSubmit={upload}>
          <label className="wide"><span>File *</span>
            <input type="file" accept=".csv,.xlsx" onChange={(e) => setFile(e.target.files[0])} /></label>
          <label><span>Source (used when the file has no source column)</span>
            <input value={source} onChange={(e) => setSource(e.target.value)} list="source-list" />
            <datalist id="source-list">
              <option>CSV Import</option><option>Public Directory</option><option>Manual Entry</option><option>TEST_DATA</option>
            </datalist></label>
          <label><span>Search keyword that found these (optional)</span>
            <input value={keyword} onChange={(e) => setKeyword(e.target.value)} list="kw-list" />
            <datalist id="kw-list">{meta.search_keywords.map((k) => <option key={k}>{k}</option>)}</datalist></label>
          <label><span>Default category (optional)</span>
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">(from file / shop name)</option>{categories.map((c) => <option key={c}>{c}</option>)}
            </select></label>
          <div className="wide"><button className="primary" disabled={busy || !file}>{busy ? "Importing…" : "Import"}</button>
            <span className="muted small"> Use source “TEST_DATA” for test files – they are hidden from lists and exports and can be purged.</span></div>
        </form>
        <ErrorBox error={error} />
        {result && (
          <>
            {result.status === "running" && <div className="notice">Processing in background… {result.progress
              ? `${(result.progress.new_count + result.progress.duplicate_count + result.progress.possible_duplicate_count + result.progress.invalid_count).toLocaleString("en-IN")} of ${result.total.toLocaleString("en-IN")} rows done` : ""}</div>}
            {result.status === "failed" && <div className="error">Import failed: {result.message}</div>}
            {result.status === "completed" && <Summary s={result} />}
            {result.ignored_columns?.length > 0 && <p className="small">Ignored columns: {result.ignored_columns.join(", ")}</p>}
            {result.errors?.length > 0 && (
              <details open={result.errors.length < 20}><summary>{result.errors.length} invalid row(s)</summary>
                <table className="mini"><tbody>
                  {result.errors.map((e, i) => <tr key={i}><td>Row {e.row ?? "–"}</td><td>{e.shop_name}</td><td>{e.reason}</td></tr>)}
                </tbody></table>
              </details>
            )}
          </>
        )}
      </Panel>

      <div className="grid-2">
        <Panel title="Government offices">
          <p className="small muted">Columns: name, office_type, address, village, taluka, district, latitude, longitude, phone.
            Office types: {meta.office_types.join(", ")}.</p>
          <input type="file" accept=".csv,.xlsx" onChange={(e) => e.target.files[0] && uploadSimple("/import/government-offices", e.target.files[0])} />
        </Panel>
        <Panel title="Talukas & villages (master data)">
          <p className="small muted">Columns: district, taluka, location, type (city/town/village/area), pincode, latitude, longitude.
            Talukas are also created automatically from business imports.</p>
          <input type="file" accept=".csv,.xlsx" onChange={(e) => e.target.files[0] && uploadSimple("/import/geo", e.target.files[0])} />
        </Panel>
      </div>

      <Panel title="Recent imports">
        <table className="data">
          <thead><tr><th>#</th><th>When</th><th>File</th><th>Source</th><th>Rows</th><th>New</th><th>Dup</th><th>Possible</th><th>Invalid</th><th>Status</th></tr></thead>
          <tbody>{(runs.data?.items || []).map((r) => (
            <tr key={r.id}><td>{r.id}</td><td>{new Date(r.created_at).toLocaleString("en-IN")}</td><td>{r.file_name}</td><td>{r.source}</td>
              <td>{r.total_results}</td><td>{r.new_count}</td><td>{r.duplicate_count}</td><td>{r.possible_duplicate_count}</td>
              <td>{r.invalid_count}</td><td>{r.status}</td></tr>
          ))}</tbody>
        </table>
      </Panel>
    </>
  );
}
