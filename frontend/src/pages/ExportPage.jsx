import { useState } from "react";
import BusinessFilters, { EMPTY_FILTERS, toParams } from "../components/BusinessFilters";
import { Panel } from "../components/ui";
import { useApi, useMeta } from "../hooks/useApi";
import { api } from "../services/api";

const PRESETS = [
  ["All Pune Xerox shops", { district: "Pune", category: "Xerox" }],
  ["All Nagpur shops", { district: "Nagpur" }],
  ["Shops with WhatsApp", { has_whatsapp: "true" }],
  ["High-score leads (60+)", { min_score: "60" }],
  ["Uncontacted leads", { contacted: "false", lead_status: "New,Not Contacted" }],
  ["Near Talathi offices (1 km)", { near_office_m: "1000", office_type: "Talathi Office" }],
  ["Follow-ups due", { followup_due: "true", sort: "followup" }],
];

export default function ExportPage() {
  const { meta, categories, sources } = useMeta();
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS });
  const params = toParams(filters);
  const count = useApi("/businesses", { ...params, page_size: 1 });
  const [busy, setBusy] = useState(false);

  async function go(p) {
    setBusy(true);
    try { await api.download("/export/csv", p); } catch (e) { alert(e.message); } finally { setBusy(false); }
  }

  return (
    <>
      <div className="page-head"><div><h1>Export</h1>
        <p className="muted">Marketing-ready CSV: normalised phone, WhatsApp link, categories, score reasons, lead status and nearest government office.</p></div></div>
      <Panel title="Quick exports">
        <div className="presets">
          {PRESETS.map(([label, p]) => (
            <button key={label} onClick={() => setFilters({ ...EMPTY_FILTERS, ...p })}>{label}</button>
          ))}
        </div>
      </Panel>
      <Panel title="Filters">
        <BusinessFilters value={filters} onChange={setFilters} meta={meta} categories={categories} sources={sources} />
      </Panel>
      <Panel>
        <div className="row-gap">
          <button className="primary" disabled={busy || !count.data?.total} onClick={() => go(params)}>
            {busy ? "Preparing…" : `⬇ Download CSV (${(count.data?.total ?? 0).toLocaleString("en-IN")} rows)`}
          </button>
          <span className="muted small">Confirmed duplicates and TEST_DATA are excluded unless you choose them.</span>
        </div>
      </Panel>
    </>
  );
}
