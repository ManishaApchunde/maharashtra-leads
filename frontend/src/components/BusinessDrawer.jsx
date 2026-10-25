import { useEffect, useState } from "react";
import { api } from "../services/api";
import { Badge, ErrorBox, ScoreBadge } from "./ui";

const EDITABLE = [
  ["shop_name", "Shop name"], ["contact_name", "Contact name"], ["phone", "Phone"],
  ["alternate_phone", "Alternate phone"], ["whatsapp_number", "WhatsApp"], ["email", "Email"],
  ["website", "Website"], ["address", "Address"], ["area", "Area"], ["village", "Village"],
  ["city", "City"], ["taluka", "Taluka"], ["district", "District"], ["pincode", "PIN code"],
  ["latitude", "Latitude"], ["longitude", "Longitude"], ["google_maps_url", "Google Maps URL"],
];

export default function BusinessDrawer({ id, meta, categories, onClose, onSaved }) {
  const [b, setB] = useState(null);
  const [form, setForm] = useState({});
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!id) return;
    setB(null); setError(null); setEditing(false);
    api.get(`/businesses/${id}`).then((d) => { setB(d); setForm(d); }).catch(setError);
  }, [id]);

  if (!id) return null;

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function save(patch) {
    setSaving(true); setError(null);
    try {
      const d = await api.put(`/businesses/${id}`, patch);
      setB(d); setForm(d); setEditing(false); onSaved?.(d);
    } catch (e) { setError(e); } finally { setSaving(false); }
  }

  function saveAll() {
    const patch = {};
    for (const [k] of EDITABLE) {
      if ((form[k] ?? "") !== (b[k] ?? "")) {
        patch[k] = k === "latitude" || k === "longitude" ? (form[k] === "" ? null : Number(form[k])) : (form[k] || null);
      }
    }
    if (JSON.stringify(form.category_names) !== JSON.stringify(b.category_names)) patch.categories = form.category_names;
    save(patch);
  }

  function saveLead() {
    save({
      lead_status: form.lead_status, response_status: form.response_status || null,
      notes: form.notes || null, next_followup_date: form.next_followup_date || null,
      demo_given: !!form.demo_given, converted: !!form.converted, contacted: !!form.contacted,
      verification_status: form.verification_status,
    });
  }

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
        <ErrorBox error={error} />
        {!b ? <p className="muted">Loading…</p> : (
          <>
            <h2>{b.shop_name}</h2>
            <div className="badges">
              {b.category_names.map((c) => <Badge key={c}>{c}</Badge>)}
              {b.is_test_data && <Badge tone="warn">TEST_DATA</Badge>}
              {b.duplicate_status !== "unique" && <Badge tone="warn">{b.duplicate_status.replace("_", " ")}</Badge>}
              <Badge tone={b.verification_status === "verified" ? "good" : ""}>{b.verification_status}</Badge>
            </div>

            <div className="drawer-grid">
              <div><span className="k">Phone</span>{b.normalized_phone || <em className="muted">{b.phone || "none"}</em>}</div>
              <div><span className="k">WhatsApp</span>{b.whatsapp_number
                ? <a href={`https://wa.me/91${b.whatsapp_number}`} target="_blank" rel="noreferrer">{b.whatsapp_number}</a>
                : <em className="muted">none</em>}</div>
              <div><span className="k">Contact</span>{b.contact_name || <em className="muted">not known</em>}</div>
              <div><span className="k">Location</span>{[b.area, b.city || b.village, b.taluka, b.district].filter(Boolean).join(", ") || "–"}</div>
              <div className="wide"><span className="k">Address</span>{b.address || "–"}{b.pincode && !(b.address || "").includes(b.pincode) ? ` ${b.pincode}` : ""}</div>
              <div><span className="k">Source</span>{b.source}{b.discovered_keyword ? ` · “${b.discovered_keyword}”` : ""}</div>
              <div><span className="k">Nearest gov. office</span>{b.nearest_gov_office_name
                ? `${b.nearest_gov_office_name} (${Math.round(b.nearest_gov_office_m)} m)` : <em className="muted">none within 2 km</em>}</div>
              {b.google_maps_url && <div><a href={b.google_maps_url} target="_blank" rel="noreferrer">Open map ↗</a></div>}
            </div>

            <h3>Lead score <ScoreBadge score={b.lead_score} /></h3>
            <p className="muted small">A marketing-priority checklist, not a prediction.</p>
            <table className="mini">
              <tbody>
                {b.score_breakdown.length ? b.score_breakdown.map((x) => (
                  <tr key={x.factor}><td>{x.factor}</td><td className="num">+{x.points}</td></tr>
                )) : <tr><td className="muted">No scoring factors matched</td><td /></tr>}
              </tbody>
            </table>

            {b.quality_flags.length > 0 && (
              <p className="small">Data issues: {b.quality_flags.map((f) => <Badge key={f} tone="warn">{f.replaceAll("_", " ")}</Badge>)}</p>
            )}

            <h3>Marketing</h3>
            <div className="form-grid">
              <label><span>Lead status</span>
                <select value={form.lead_status} onChange={(e) => set("lead_status", e.target.value)}>
                  {meta.lead_statuses.map((s) => <option key={s}>{s}</option>)}
                </select></label>
              <label><span>Verification</span>
                <select value={form.verification_status} onChange={(e) => set("verification_status", e.target.value)}>
                  {meta.verification_statuses.map((s) => <option key={s}>{s}</option>)}
                </select></label>
              <label><span>Response</span>
                <input value={form.response_status || ""} placeholder="e.g. asked for price" onChange={(e) => set("response_status", e.target.value)} /></label>
              <label><span>Next follow-up</span>
                <input type="date" value={form.next_followup_date || ""} onChange={(e) => set("next_followup_date", e.target.value)} /></label>
              <label className="check"><input type="checkbox" checked={!!form.contacted} onChange={(e) => set("contacted", e.target.checked)} /> Contacted</label>
              <label className="check"><input type="checkbox" checked={!!form.demo_given} onChange={(e) => set("demo_given", e.target.checked)} /> Demo given</label>
              <label className="check"><input type="checkbox" checked={!!form.converted} onChange={(e) => set("converted", e.target.checked)} /> Converted</label>
              <label className="wide"><span>Notes</span>
                <textarea rows={3} value={form.notes || ""} onChange={(e) => set("notes", e.target.value)} /></label>
            </div>
            <button className="primary" disabled={saving} onClick={saveLead}>{saving ? "Saving…" : "Save lead update"}</button>
            {b.contacted_at && <span className="muted small"> First contacted {new Date(b.contacted_at).toLocaleDateString("en-IN")}</span>}

            <h3>
              Business details{" "}
              <button className="link" onClick={() => setEditing((v) => !v)}>{editing ? "cancel" : "edit"}</button>
            </h3>
            {editing && (
              <>
                <div className="form-grid">
                  {EDITABLE.map(([k, label]) => (
                    <label key={k}><span>{label}</span>
                      <input value={form[k] ?? ""} onChange={(e) => set(k, e.target.value)} /></label>
                  ))}
                  <label className="wide"><span>Categories</span>
                    <div className="chips">
                      {categories.map((c) => (
                        <label key={c} className="chip">
                          <input type="checkbox" checked={form.category_names?.includes(c)}
                            onChange={(e) => set("category_names", e.target.checked
                              ? [...(form.category_names || []), c] : form.category_names.filter((x) => x !== c))} />
                          {c}
                        </label>
                      ))}
                    </div>
                  </label>
                </div>
                <button className="primary" disabled={saving} onClick={saveAll}>Save details</button>
                <p className="muted small">Phone numbers, district and PIN are re-cleaned on save.</p>
              </>
            )}
            <p className="muted small">#{b.id} · added {new Date(b.created_at).toLocaleString("en-IN")}
              {b.last_verified_at && ` · verified ${new Date(b.last_verified_at).toLocaleDateString("en-IN")}`}</p>
          </>
        )}
      </aside>
    </div>
  );
}
