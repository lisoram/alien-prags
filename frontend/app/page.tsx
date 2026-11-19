"use client";

import { useCallback, useEffect, useState } from "react";

type ServiceStatus = { status: "ok" } | { status: "error"; message: string };

type HealthResponse = {
  status: "ok" | "degraded";
  services: Record<string, ServiceStatus>;
};

// Inlined at build time by Next.js, so it must be set when building the image.
const API_URL = process.env.NEXT_PUBLIC_API_URL;

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [unreachable, setUnreachable] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      if (!API_URL) throw new Error("NEXT_PUBLIC_API_URL is not set");
      const res = await fetch(`${API_URL}/api/v1/health`, { cache: "no-store" });
      // 503 still carries a useful body naming the failing service.
      const body = await res.json();
      if (!body.services) {
        throw new Error(body?.error?.message ?? `Unexpected response (HTTP ${res.status})`);
      }
      setHealth(body as HealthResponse);
      setUnreachable(null);
    } catch (err) {
      setHealth(null);
      setUnreachable(err instanceof Error ? err.message : String(err));
    } finally {
      setCheckedAt(new Date());
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial fetch on mount; refresh() only sets state after awaiting the network.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  return (
    <main className="mx-auto w-full max-w-3xl p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Service status</h1>
        <button
          onClick={refresh}
          disabled={loading}
          className="rounded-md border border-current px-4 py-2 text-sm disabled:opacity-50"
        >
          {loading ? "Checking…" : "Refresh"}
        </button>
      </div>

      {unreachable && (
        <div role="alert" className="mt-6 rounded-md border border-red-500 bg-red-500/10 p-4 text-red-600">
          <p className="font-semibold">Backend unreachable</p>
          <p className="text-sm">{unreachable}</p>
        </div>
      )}

      {health && (
        <>
          <p className="mt-6 text-sm">
            Overall:{" "}
            <span className={health.status === "ok" ? "font-semibold text-green-600" : "font-semibold text-red-600"}>
              {health.status}
            </span>
          </p>
          <ul className="mt-4 grid gap-4 sm:grid-cols-2">
            {Object.entries(health.services).map(([name, svc]) => (
              <li
                key={name}
                className={`rounded-md border p-4 ${
                  svc.status === "ok" ? "border-green-500 bg-green-500/10" : "border-red-500 bg-red-500/10"
                }`}
              >
                <p className="font-semibold capitalize">{name}</p>
                <p className={svc.status === "ok" ? "text-green-600" : "text-red-600"}>{svc.status}</p>
                {svc.status === "error" && <p className="mt-1 text-sm break-words">{svc.message}</p>}
              </li>
            ))}
          </ul>
        </>
      )}

      {checkedAt && <p className="mt-6 text-xs opacity-70">Last checked: {checkedAt.toLocaleString()}</p>}
    </main>
  );
}
