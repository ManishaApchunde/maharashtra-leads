import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";

/** GET `path` with `params`; refetches when they change. Returns {data, error, loading, reload}. */
export function useApi(path, params) {
  const key = JSON.stringify(params || {});
  const [state, setState] = useState({ data: null, error: null, loading: !!path });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!path) return;
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    api.get(path, params)
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((error) => alive && setState({ data: null, error, loading: false }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

/** Reference lists used by many pages (statuses, categories, sources, keywords). */
export function useMeta() {
  const meta = useApi("/meta");
  const cats = useApi("/categories");
  const sources = useApi("/sources");
  return {
    meta: meta.data || { lead_statuses: [], office_types: [], search_keywords: [], verification_statuses: [] },
    categories: (cats.data || []).map((c) => c.name),
    sources: (sources.data || []).map((s) => s.source_name),
  };
}
