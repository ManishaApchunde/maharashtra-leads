import { useState } from "react";
import { Link } from "react-router-dom";
import GeoFilter from "../components/GeoFilter";
import { ErrorBox, Panel, Stat } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

// Where each issue's "view" link goes on the Businesses page
const LINKS = {
  missing_phone: "quality_flag=missing_phone", invalid_phone: "quality_flag=invalid_phone",
  missing_address: "quality_flag=missing_address", missing_district: "quality_flag=missing_district",
  unrecognized_district: "quality_flag=unrecognized_district", missing_pincode: "quality_flag=missing_pincode",
  bad_pincode: "quality_flag=pincode_outside_maharashtra", duplicate_candidates: "duplicate_status=possible_duplicate",
  unverified: "verification_status=unverified",
};

export default function DataQuality() {
  const [geo, setGeo] = useState({ district: "", taluka: "", city: "" });
  const [testData, setTestData] = useState(false);
  const { data, error, reload } = useApi("/data-quality", { ...geo, include_test_data: testData || "" });
  const [msg, setMsg] = useState(null);

  async function run(path, method = "post") {
    setMsg("Working…");
    try { const r = await api[method](path); setMsg(JSON.stringify(r)); reload(); } catch (e) { setMsg(e.message); }
  }

  return (
    <>
      <div className="page-head"><div><h1>Data quality</h1>
        <p className="muted">Problems are flagged, never auto-fixed with guessed values.</p></div>
        <label className="check"><input type="checkbox" checked={testData} onChange={(e) => setTestData(e.target.checked)} /> Include TEST_DATA</label>
      </div>
      <GeoFilter value={geo} onChange={setGeo} showArea={false} />
      <ErrorBox error={error} />
      {data && (
        <>
          <div className="stats">
            <Stat label="Records checked" value={data.total.toLocaleString("en-IN")} />
            <Stat label="Pending duplicate pairs" value={<Link to="/duplicates">{data.pending_duplicate_pairs}</Link>} tone={data.pending_duplicate_pairs ? "warn" : ""} />
          </div>
          <Panel title="Issues">
            <table className="data">
              <thead><tr><th>Issue</th><th className="num">Records</th><th className="num">% of total</th><th /></tr></thead>
              <tbody>
                {data.issues.map((i) => (
                  <tr key={i.key}>
                    <td>{i.description}</td>
                    <td className="num">{i.count.toLocaleString("en-IN")}</td>
                    <td className="num">{data.total ? Math.round((i.count / data.total) * 100) : 0}%</td>
                    <td>{LINKS[i.key] && i.count > 0 && (
                      <Link to={`/businesses?${LINKS[i.key]}${["district", "taluka", "city"].map((k) => geo[k] ? `&${k}=${encodeURIComponent(geo[k])}` : "").join("")}${testData ? "&include_test_data=true" : ""}`}>view →</Link>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </>
      )}
      <Panel title="Maintenance">
        <div className="row-gap">
          <button onClick={() => run("/admin/rescore")}>Recalculate proximity &amp; lead scores</button>
          <button onClick={() => run("/duplicates/check")}>Re-run duplicate check</button>
          <button onClick={() => window.confirm("Delete every TEST_DATA record?") && run("/admin/test-data", "del")}>Purge TEST_DATA</button>
        </div>
        {msg && <div className="notice small">{msg}</div>}
      </Panel>
    </>
  );
}
