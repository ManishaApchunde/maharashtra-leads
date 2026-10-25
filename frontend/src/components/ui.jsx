import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function Stat({ label, value, hint, tone }) {
  return (
    <div className={`stat ${tone || ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value ?? "–"}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function Panel({ title, actions, children }) {
  return (
    <section className="panel">
      {(title || actions) && (
        <header className="panel-head">
          <h2>{title}</h2>
          <div className="panel-actions">{actions}</div>
        </header>
      )}
      {children}
    </section>
  );
}

/** Horizontal bar chart: data = [{name, count}] */
export function BarBlock({ data, height }) {
  if (!data || !data.length) return <p className="muted">No data yet.</p>;
  const h = height || Math.max(160, data.length * 28 + 30);
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
        <CartesianGrid horizontal={false} stroke="var(--grid)" />
        <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: "var(--muted)" }} />
        <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 12, fill: "var(--text)" }} />
        <Tooltip cursor={{ fill: "var(--hover)" }} />
        <Bar dataKey="count" fill="var(--accent)" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Pager({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pager">
      <span className="muted">{total.toLocaleString("en-IN")} records</span>
      <button disabled={page <= 1} onClick={() => onPage(page - 1)}>‹ Prev</button>
      <span>Page {page} / {pages}</span>
      <button disabled={page >= pages} onClick={() => onPage(page + 1)}>Next ›</button>
    </div>
  );
}

export function Badge({ children, tone }) {
  return <span className={`badge ${tone || ""}`}>{children}</span>;
}

export function ScoreBadge({ score }) {
  const tone = score >= 60 ? "good" : score >= 35 ? "mid" : "low";
  return <span className={`score ${tone}`}>{score}</span>;
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return <div className="error">⚠ {String(error.message || error)}</div>;
}
