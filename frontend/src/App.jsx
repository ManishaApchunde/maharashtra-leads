import { NavLink, Route, Routes } from "react-router-dom";
import { useApi } from "./hooks/useApi";
import Businesses from "./pages/Businesses";
import Collection from "./pages/Collection";
import Dashboard from "./pages/Dashboard";
import DataQuality from "./pages/DataQuality";
import Duplicates from "./pages/Duplicates";
import ExportPage from "./pages/ExportPage";
import GovOffices from "./pages/GovOffices";
import ImportPage from "./pages/ImportPage";

const NAV = [
  ["/", "Dashboard"], ["/businesses", "Businesses & leads"], ["/duplicates", "Duplicate review"],
  ["/import", "Import"], ["/export", "Export"], ["/collection", "Data collection"],
  ["/government-offices", "Government offices"], ["/data-quality", "Data quality"],
];

export default function App() {
  const health = useApi("/health");
  return (
    <div className="app">
      <nav className="sidebar">
        <div className="brand">
          <div className="brand-mark">LR</div>
          <div><strong>Land Recorder</strong><div className="small">Maharashtra lead database</div></div>
        </div>
        {NAV.map(([to, label]) => (
          <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>{label}</NavLink>
        ))}
        <div className={`api-status ${health.error ? "bad" : health.data ? "good" : ""}`}>
          {health.error ? "API offline – start the backend" : health.data ? "API connected" : "Connecting…"}
        </div>
      </nav>
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/businesses" element={<Businesses />} />
          <Route path="/duplicates" element={<Duplicates />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/export" element={<ExportPage />} />
          <Route path="/collection" element={<Collection />} />
          <Route path="/government-offices" element={<GovOffices />} />
          <Route path="/data-quality" element={<DataQuality />} />
        </Routes>
      </main>
    </div>
  );
}
