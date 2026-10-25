import { useState } from "react";
import { Link } from "react-router-dom";
import GeoFilter from "../components/GeoFilter";
import { BarBlock, ErrorBox, Panel, Stat } from "../components/ui";
import { useApi } from "../hooks/useApi";

const n = (v) => (v ?? 0).toLocaleString("en-IN");

export default function Dashboard() {
  const [geo, setGeo] = useState({ district: "", taluka: "", city: "" });
  const [testData, setTestData] = useState(false);
  const { data, error, loading } = useApi("/analytics", { ...geo, include_test_data: testData || "" });
  const t = data?.totals || {};
  const scope = [geo.city, geo.taluka, geo.district].filter(Boolean).join(", ") || "All Maharashtra";

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">{scope}{loading ? " · loading…" : ""}</p>
        </div>
        <label className="check"><input type="checkbox" checked={testData} onChange={(e) => setTestData(e.target.checked)} /> Include TEST_DATA</label>
      </div>
      <GeoFilter value={geo} onChange={setGeo} showArea={false} />
      <ErrorBox error={error} />

      <div className="stats">
        <Stat label="Total businesses" value={n(t.total)} />
        <Stat label="Districts covered" value={`${n(t.districts_covered)} / ${n(t.districts_in_master)}`} />
        <Stat label="Talukas covered" value={n(t.talukas_covered)} hint={`${n(t.talukas_in_master)} in master list`} />
        <Stat label="With phone" value={n(t.with_phone)} />
        <Stat label="With WhatsApp" value={n(t.with_whatsapp)} />
        <Stat label="Verified" value={n(t.verified)} tone="good" />
        <Stat label="Unverified" value={n(t.unverified)} />
        <Stat label="Duplicate candidates" value={<Link to="/duplicates">{n(t.duplicate_candidates)}</Link>} tone={t.duplicate_candidates ? "warn" : ""} />
        <Stat label="New leads" value={n(t.new_leads)} />
        <Stat label="Contacted" value={n(t.contacted)} />
        <Stat label="Interested" value={n(t.interested)} />
        <Stat label="Converted" value={n(t.converted)} tone="good" />
        <Stat label="Score 60+" value={n(t.high_score)} hint={`avg score ${t.avg_score ?? 0}`} />
        <Stat label="≤1 km from gov. office" value={n(t.near_gov_office_1km)} />
      </div>

      <div className="grid-2">
        <Panel title={geo.district ? (geo.taluka ? "Businesses by city" : "Businesses by taluka") : "Businesses by district"}>
          <BarBlock data={geo.district ? (geo.taluka ? data?.by_city : data?.by_taluka) : data?.by_district} />
        </Panel>
        <Panel title="Businesses by category"><BarBlock data={data?.by_category} /></Panel>
        <Panel title="Businesses by lead status"><BarBlock data={data?.by_lead_status} /></Panel>
        <Panel title="Businesses by source"><BarBlock data={data?.by_source} /></Panel>
        <Panel title="Lead score bands"><BarBlock data={data?.by_score_band} /></Panel>
      </div>
    </>
  );
}
