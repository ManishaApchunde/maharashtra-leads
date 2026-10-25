import { useApi } from "../hooks/useApi";

/**
 * Cascading location filter: All Maharashtra -> District -> Taluka -> City/Town/Village -> Area.
 * value = { district, taluka, city, area } (names); onChange receives the full new value.
 */
export default function GeoFilter({ value, onChange, showArea = true }) {
  const districts = useApi("/districts");
  const districtObj = (districts.data || []).find((d) => d.name === value.district);
  const talukas = useApi(districtObj ? `/districts/${districtObj.id}/talukas` : null);
  const cities = useApi(value.district ? "/filters/cities" : null, { district: value.district, taluka: value.taluka });
  const areas = useApi(showArea && value.city ? "/filters/areas" : null, { district: value.district, city: value.city });

  const set = (patch) => onChange({ ...value, ...patch });

  return (
    <div className="geo-filter">
      <label>
        <span>District</span>
        <select value={value.district || ""} onChange={(e) => set({ district: e.target.value, taluka: "", city: "", area: "" })}>
          <option value="">All Maharashtra</option>
          {(districts.data || []).map((d) => (
            <option key={d.id} value={d.name}>{d.name}{d.business_count ? ` (${d.business_count})` : ""}</option>
          ))}
        </select>
      </label>
      <label>
        <span>Taluka</span>
        <select disabled={!value.district} value={value.taluka || ""} onChange={(e) => set({ taluka: e.target.value, city: "", area: "" })}>
          <option value="">All talukas</option>
          {(talukas.data || []).map((t) => <option key={t.id} value={t.name}>{t.name}</option>)}
        </select>
      </label>
      <label>
        <span>City / Town / Village</span>
        <select disabled={!value.district} value={value.city || ""} onChange={(e) => set({ city: e.target.value, area: "" })}>
          <option value="">All</option>
          {(cities.data || []).map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
      {showArea && (
        <label>
          <span>Area</span>
          <select disabled={!value.city} value={value.area || ""} onChange={(e) => set({ area: e.target.value })}>
            <option value="">All areas</option>
            {(areas.data || []).map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>
      )}
    </div>
  );
}
