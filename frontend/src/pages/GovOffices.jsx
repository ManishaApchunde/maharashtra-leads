import { useState } from "react";
import { Link } from "react-router-dom";
import { ErrorBox, Panel } from "../components/ui";
import { useApi, useMeta } from "../hooks/useApi";
import { api } from "../services/api";

const EMPTY = { name: "", office_type: "Talathi Office", address: "", village: "", taluka: "", district: "",
  latitude: "", longitude: "", phone: "" };

export default function GovOffices() {
  const { meta } = useMeta();
  const [filter, setFilter] = useState({ district: "", office_type: "" });
  const { data, error, reload } = useApi("/government-offices", filter);
  const districts = useApi("/districts");
  const [form, setForm] = useState(EMPTY);
  const [msg, setMsg] = useState(null);

  async function add(e) {
    e.preventDefault();
    try {
      await api.post("/government-offices", {
        ...form, latitude: form.latitude === "" ? null : Number(form.latitude),
        longitude: form.longitude === "" ? null : Number(form.longitude),
      });
      setForm(EMPTY); setMsg("Saved. Click “Recalculate” to update nearby shops’ scores."); reload();
    } catch (err) { setMsg(err.message); }
  }

  async function recompute() {
    setMsg("Recalculating…");
    try {
      const r = await api.post("/government-offices/recompute-proximity");
      setMsg(`Updated distances for ${r.distances_updated} shops and recalculated ${r.scores_recalculated} scores.`);
    } catch (err) { setMsg(err.message); }
  }

  async function remove(id) {
    if (!window.confirm("Delete this office?")) return;
    await api.del(`/government-offices/${id}`); reload();
  }

  return (
    <>
      <div className="page-head"><div><h1>Government offices</h1>
        <p className="muted">Talathi, Tehsil, Setu and Sub-Registrar offices. Shops within 1–2 km score higher.</p></div>
        <div className="row-gap">
          <Link to="/businesses?near_office_m=1000"><button>Shops within 1 km →</button></Link>
          <button className="primary" onClick={recompute}>Recalculate proximity &amp; scores</button>
        </div>
      </div>
      {msg && <div className="notice">{msg}</div>}
      <Panel title="Add an office">
        <form className="form-grid" onSubmit={add}>
          <label><span>Name *</span><input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label><span>Type *</span>
            <select value={form.office_type} onChange={(e) => setForm({ ...form, office_type: e.target.value })}>
              {meta.office_types.map((t) => <option key={t}>{t}</option>)}</select></label>
          <label><span>District</span>
            <select value={form.district} onChange={(e) => setForm({ ...form, district: e.target.value })}>
              <option value="" />{(districts.data || []).map((d) => <option key={d.id}>{d.name}</option>)}</select></label>
          {["taluka", "village", "address", "latitude", "longitude", "phone"].map((k) => (
            <label key={k}><span>{k}</span><input value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></label>
          ))}
          <div className="wide"><button className="primary">Save office</button>
            <span className="muted small"> Coordinates are required for distance calculation. Bulk upload is on the Import page.</span></div>
        </form>
      </Panel>
      <Panel title={`Offices (${data?.length ?? 0})`} actions={
        <div className="row-gap">
          <select value={filter.district} onChange={(e) => setFilter({ ...filter, district: e.target.value })}>
            <option value="">All districts</option>{(districts.data || []).map((d) => <option key={d.id}>{d.name}</option>)}</select>
          <select value={filter.office_type} onChange={(e) => setFilter({ ...filter, office_type: e.target.value })}>
            <option value="">All types</option>{meta.office_types.map((t) => <option key={t}>{t}</option>)}</select>
        </div>}>
        <ErrorBox error={error} />
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>Name</th><th>Type</th><th>Village</th><th>Taluka</th><th>District</th><th>Coordinates</th><th>Phone</th><th /></tr></thead>
            <tbody>
              {(data || []).map((o) => (
                <tr key={o.id}><td>{o.name}</td><td>{o.office_type}</td><td>{o.village}</td><td>{o.taluka}</td><td>{o.district}</td>
                  <td className="small">{o.latitude != null ? `${o.latitude}, ${o.longitude}` : <span className="muted">missing</span>}</td>
                  <td>{o.phone}</td><td><button className="link" onClick={() => remove(o.id)}>delete</button></td></tr>
              ))}
              {data?.length === 0 && <tr><td colSpan={8} className="muted center">No offices yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
