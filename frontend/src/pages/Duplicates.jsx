import { useState } from "react";
import { ErrorBox, Pager, Panel } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

const FIELDS = [
  ["shop_name", "Name"], ["normalized_phone", "Phone"], ["whatsapp_number", "WhatsApp"],
  ["address", "Address"], ["area", "Area"], ["city", "City"], ["taluka", "Taluka"],
  ["district", "District"], ["pincode", "PIN"], ["source", "Source"], ["lead_status", "Lead status"],
];

function Side({ b, label }) {
  return (
    <div className="dup-side">
      <div className="muted small">{label} · #{b.id} · added {new Date(b.created_at).toLocaleDateString("en-IN")}</div>
      <table className="mini">
        <tbody>
          {FIELDS.map(([k, l]) => <tr key={k}><td className="muted">{l}</td><td>{b[k] ?? <em className="muted">–</em>}</td></tr>)}
          <tr><td className="muted">Coords</td><td>{b.latitude != null ? `${b.latitude.toFixed(5)}, ${b.longitude.toFixed(5)}` : "–"}</td></tr>
        </tbody>
      </table>
    </div>
  );
}

export default function Duplicates() {
  const [status, setStatus] = useState("pending");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);
  const { data, error, reload } = useApi("/duplicates", { status, page, page_size: 10 });

  async function act(id, action, keep) {
    setBusy(id); setMsg(null);
    try {
      const r = action === "confirm"
        ? await api.post(`/duplicates/${id}/confirm`, { keep, merge_missing_fields: true })
        : await api.post(`/duplicates/${id}/reject`);
      setMsg(action === "confirm"
        ? `Kept #${r.kept_id}; #${r.duplicate_id} marked as duplicate (not deleted).${r.filled_fields.length ? ` Filled: ${r.filled_fields.join(", ")}` : ""}`
        : "Marked as different businesses.");
      reload();
    } catch (e) { setMsg(e.message); } finally { setBusy(null); }
  }

  async function recheck() {
    setMsg("Re-checking…");
    try {
      const r = await api.post("/duplicates/check", {});
      setMsg(`Checked ${r.checked} records, ${r.new_candidate_pairs} new pairs found.`);
      reload();
    } catch (e) { setMsg(e.message); }
  }

  return (
    <>
      <div className="page-head">
        <div><h1>Duplicate review</h1>
          <p className="muted">Nothing is deleted automatically. Confirm keeps both rows but hides the duplicate from lists and exports.</p></div>
        <div className="row-gap">
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="pending">Pending</option><option value="confirmed">Confirmed</option><option value="rejected">Rejected</option>
          </select>
          <button onClick={recheck}>Re-run duplicate check</button>
        </div>
      </div>
      <ErrorBox error={error} />
      {msg && <div className="notice">{msg}</div>}
      {data?.items?.length === 0 && <Panel><p className="muted center">No {status} duplicate pairs. 🎉</p></Panel>}
      {(data?.items || []).map((c) => (
        <Panel key={c.id} title={<>Match score {c.match_score} <span className="muted small">· {c.reasons.join(" · ")}</span></>}>
          <div className="dup-pair">
            <Side b={c.business} label="Newer record" />
            <Side b={c.matched_business} label="Existing record" />
          </div>
          {status === "pending" && (
            <div className="row-gap">
              <button className="primary" disabled={busy === c.id} onClick={() => act(c.id, "confirm", "matched")}>Same shop – keep existing</button>
              <button disabled={busy === c.id} onClick={() => act(c.id, "confirm", "business")}>Same shop – keep newer</button>
              <button disabled={busy === c.id} onClick={() => act(c.id, "reject")}>Different shops</button>
            </div>
          )}
        </Panel>
      ))}
      {data && data.total > 10 && <Pager page={page} pageSize={10} total={data.total} onPage={setPage} />}
    </>
  );
}
