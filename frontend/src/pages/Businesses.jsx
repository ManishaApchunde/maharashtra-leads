import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import BusinessDrawer from "../components/BusinessDrawer";
import BusinessFilters, { EMPTY_FILTERS, toParams } from "../components/BusinessFilters";
import { Badge, ErrorBox, Pager, Panel, ScoreBadge } from "../components/ui";
import { useApi, useMeta } from "../hooks/useApi";
import { api } from "../services/api";

const NEW_BIZ = { shop_name: "", contact_name: "", phone: "", whatsapp_number: "", address: "", area: "",
  city: "", taluka: "", district: "", pincode: "", category: "", source: "Manual Entry", notes: "" };

export default function Businesses() {
  const [searchParams] = useSearchParams();
  const initial = { ...EMPTY_FILTERS };
  searchParams.forEach((v, k) => { if (k in initial) initial[k] = v; });

  const [filters, setFilters] = useState(initial);
  const [debounced, setDebounced] = useState(initial);
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState(null);
  const [adding, setAdding] = useState(false);
  const [newBiz, setNewBiz] = useState(NEW_BIZ);
  const [addMsg, setAddMsg] = useState(null);
  const { meta, categories, sources } = useMeta();

  useEffect(() => {
    const t = setTimeout(() => { setDebounced(filters); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [filters]);

  const { data, error, loading, reload } = useApi("/businesses", { ...toParams(debounced), page, page_size: 50 });

  async function addBusiness(e) {
    e.preventDefault();
    setAddMsg(null);
    try {
      const r = await api.post("/businesses", newBiz);
      if (r.outcome === "duplicate") setAddMsg({ tone: "warn", text: `Already in the database as #${r.existing_id} (${r.reasons.join(", ")}). Missing fields were filled in.` });
      else if (r.outcome === "possible_duplicate") setAddMsg({ tone: "warn", text: `Added as #${r.business.id}, flagged as a possible duplicate for review.` });
      else setAddMsg({ tone: "good", text: `Added as #${r.business.id} with score ${r.business.lead_score}.` });
      setNewBiz(NEW_BIZ); reload();
    } catch (err) { setAddMsg({ tone: "bad", text: err.message }); }
  }

  return (
    <>
      <div className="page-head">
        <div><h1>Businesses &amp; leads</h1><p className="muted">Search and filter the whole Maharashtra database.</p></div>
        <div className="row-gap">
          <button onClick={() => api.download("/export/csv", toParams(debounced)).catch((e) => alert(e.message))}>⬇ Export these results</button>
          <button className="primary" onClick={() => setAdding((v) => !v)}>{adding ? "Close" : "+ Add business"}</button>
        </div>
      </div>

      {adding && (
        <Panel title="Add a business manually">
          <form className="form-grid" onSubmit={addBusiness}>
            {Object.keys(NEW_BIZ).filter((k) => k !== "source").map((k) => (
              <label key={k} className={k === "address" || k === "notes" ? "wide" : ""}>
                <span>{k.replaceAll("_", " ")}{k === "shop_name" ? " *" : ""}</span>
                {k === "category" ? (
                  <select value={newBiz.category} onChange={(e) => setNewBiz({ ...newBiz, category: e.target.value })}>
                    <option value="">(detect from name)</option>{categories.map((c) => <option key={c}>{c}</option>)}
                  </select>
                ) : (
                  <input required={k === "shop_name"} value={newBiz[k]} onChange={(e) => setNewBiz({ ...newBiz, [k]: e.target.value })} />
                )}
              </label>
            ))}
            <div className="wide"><button className="primary" type="submit">Save</button>
              <span className="muted small"> Goes through the same cleaning and duplicate checks as imports. Leave unknown fields blank.</span></div>
          </form>
          {addMsg && <div className={`notice ${addMsg.tone}`}>{addMsg.text}</div>}
        </Panel>
      )}

      <Panel>
        <BusinessFilters value={filters} onChange={setFilters} meta={meta} categories={categories} sources={sources} />
        <div className="row-gap"><button className="link" onClick={() => setFilters({ ...EMPTY_FILTERS })}>Reset filters</button></div>
      </Panel>

      <ErrorBox error={error} />
      <Panel>
        <div className="table-wrap">
          <table className="data">
            <thead><tr>
              <th>Score</th><th>Shop</th><th>Phone</th><th>WhatsApp</th><th>Location</th><th>Categories</th>
              <th>Gov. office</th><th>Status</th><th>Source</th>
            </tr></thead>
            <tbody>
              {(data?.items || []).map((b) => (
                <tr key={b.id} onClick={() => setOpenId(b.id)} className="clickable">
                  <td><ScoreBadge score={b.lead_score} /></td>
                  <td><strong>{b.shop_name}</strong>
                    {b.duplicate_status === "possible_duplicate" && <Badge tone="warn">dup?</Badge>}
                    {b.is_test_data && <Badge tone="warn">TEST</Badge>}
                    {b.contact_name && <div className="muted small">{b.contact_name}</div>}</td>
                  <td>{b.normalized_phone || <span className="muted">{b.phone ? "invalid" : "–"}</span>}</td>
                  <td>{b.whatsapp_number ? "✓" : ""}</td>
                  <td>{[b.area, b.city || b.village].filter(Boolean).join(", ")}
                    <div className="muted small">{[b.taluka, b.district].filter(Boolean).join(", ")} {b.pincode}</div></td>
                  <td className="small">{b.category_names.join(", ")}</td>
                  <td className="small">{b.nearest_gov_office_m != null ? `${Math.round(b.nearest_gov_office_m)} m` : ""}</td>
                  <td><Badge>{b.lead_status}</Badge></td>
                  <td className="small muted">{b.source}</td>
                </tr>
              ))}
              {!loading && data?.items?.length === 0 && (
                <tr><td colSpan={9} className="muted center">No businesses match these filters. Import a CSV to get started.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {data && <Pager page={page} pageSize={50} total={data.total} onPage={setPage} />}
      </Panel>

      <BusinessDrawer id={openId} meta={meta} categories={categories}
        onClose={() => setOpenId(null)} onSaved={() => reload()} />
    </>
  );
}
