import GeoFilter from "./GeoFilter";

export const EMPTY_FILTERS = {
  q: "", district: "", taluka: "", city: "", area: "", pincode: "", category: "", lead_status: "",
  source: "", verification_status: "", duplicate_status: "", has_phone: "", has_whatsapp: "",
  contacted: "", min_score: "", near_office_m: "", office_type: "", quality_flag: "",
  include_test_data: "", followup_due: "", sort: "score",
};

/** Turns the filter form into API query params (drops blanks). */
export function toParams(f) {
  const p = {};
  Object.entries(f).forEach(([k, v]) => { if (v !== "" && v !== null && v !== undefined) p[k] = v; });
  return p;
}

const YesNo = ({ label, value, onChange }) => (
  <label><span>{label}</span>
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Any</option><option value="true">Yes</option><option value="false">No</option>
    </select>
  </label>
);

export default function BusinessFilters({ value, onChange, meta, categories, sources }) {
  const set = (patch) => onChange({ ...value, ...patch });
  return (
    <div className="filters">
      <label className="search">
        <span>Search</span>
        <input placeholder="Shop name, phone, address, city, pincode…" value={value.q}
          onChange={(e) => set({ q: e.target.value })} />
      </label>
      <GeoFilter value={value} onChange={(g) => set(g)} />
      <div className="filter-row">
        <label><span>Category</span>
          <select value={value.category} onChange={(e) => set({ category: e.target.value })}>
            <option value="">All</option>{categories.map((c) => <option key={c}>{c}</option>)}
          </select></label>
        <label><span>Lead status</span>
          <select value={value.lead_status} onChange={(e) => set({ lead_status: e.target.value })}>
            <option value="">All</option>{meta.lead_statuses.map((s) => <option key={s}>{s}</option>)}
          </select></label>
        <label><span>Min score</span>
          <input type="number" min="0" max="100" value={value.min_score} onChange={(e) => set({ min_score: e.target.value })} /></label>
        <YesNo label="WhatsApp" value={value.has_whatsapp} onChange={(v) => set({ has_whatsapp: v })} />
        <YesNo label="Phone" value={value.has_phone} onChange={(v) => set({ has_phone: v })} />
        <YesNo label="Contacted" value={value.contacted} onChange={(v) => set({ contacted: v })} />
        <label><span>PIN code</span>
          <input value={value.pincode} maxLength={6} onChange={(e) => set({ pincode: e.target.value })} /></label>
      </div>
      <div className="filter-row">
        <label><span>Near gov. office</span>
          <select value={value.near_office_m} onChange={(e) => set({ near_office_m: e.target.value })}>
            <option value="">Any distance</option><option value="500">within 500 m</option>
            <option value="1000">within 1 km</option><option value="2000">within 2 km</option>
          </select></label>
        <label><span>Office type</span>
          <select value={value.office_type} disabled={!value.near_office_m} onChange={(e) => set({ office_type: e.target.value })}>
            <option value="">Any office</option>{meta.office_types.map((s) => <option key={s}>{s}</option>)}
          </select></label>
        <label><span>Source</span>
          <select value={value.source} onChange={(e) => set({ source: e.target.value })}>
            <option value="">All</option>{sources.map((s) => <option key={s}>{s}</option>)}
          </select></label>
        <label><span>Verification</span>
          <select value={value.verification_status} onChange={(e) => set({ verification_status: e.target.value })}>
            <option value="">All</option>{meta.verification_statuses.map((s) => <option key={s}>{s}</option>)}
          </select></label>
        <label><span>Duplicates</span>
          <select value={value.duplicate_status} onChange={(e) => set({ duplicate_status: e.target.value })}>
            <option value="">Hide confirmed</option><option value="unique">Unique only</option>
            <option value="possible_duplicate">Possible duplicates</option>
            <option value="confirmed_duplicate">Confirmed duplicates</option>
          </select></label>
        <label><span>Sort</span>
          <select value={value.sort} onChange={(e) => set({ sort: e.target.value })}>
            <option value="score">Highest score</option><option value="newest">Newest</option>
            <option value="name">Name A–Z</option><option value="followup">Follow-up date</option>
            <option value="distance">Nearest gov. office</option>
          </select></label>
        <label className="check"><input type="checkbox" checked={value.followup_due === "true"}
          onChange={(e) => set({ followup_due: e.target.checked ? "true" : "" })} /> Follow-up due</label>
        <label className="check"><input type="checkbox" checked={value.include_test_data === "true"}
          onChange={(e) => set({ include_test_data: e.target.checked ? "true" : "" })} /> Include TEST_DATA</label>
      </div>
    </div>
  );
}
