"use client";

import { useEffect, useState } from "react";
import { bankitApi, SweepSummary, SweepRecord } from "@/lib/api";

const fmt = (n: number) => `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const pct = (n: number) => `${(n * 100).toFixed(2)}%`;

function StatCard({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div className={`rounded-xl border p-5 ${highlight ? "border-blue-200 bg-blue-50" : "border-zinc-200 bg-white"}`}>
      <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-2xl font-semibold ${highlight ? "text-blue-900" : "text-zinc-900"}`}>{value}</p>
      {sub && <p className="text-xs text-zinc-400 mt-1">{sub}</p>}
    </div>
  );
}

const SOURCE_LABELS: Record<string, string> = {
  stripe: "Stripe",
  w2g: "W-2G",
  direct: "Direct",
  readybucks: "ReadyBucks",
};

export default function CompliancePage() {
  const [summary, setSummary] = useState<SweepSummary | null>(null);
  const [history, setHistory] = useState<SweepRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    try {
      const [s, h] = await Promise.all([bankitApi.payments.sweepSummary(), bankitApi.payments.sweepHistory()]);
      setSummary(s);
      setHistory(h);
    } catch (e: unknown) {
      setError((e as Error).message ?? "Failed to load compliance data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  if (loading) return <div className="text-sm text-zinc-400">Loading...</div>;
  if (error) return (
    <div className="flex flex-col items-start gap-3">
      <p className="text-sm text-red-500">{error}</p>
      <button
        onClick={() => { setLoading(true); setError(""); void load(); }}
        className="text-xs font-medium px-3 py-1.5 rounded-lg border border-zinc-200 hover:bg-zinc-50 transition-colors"
      >
        Retry
      </button>
    </div>
  );
  if (!summary) return null;

  const noActivity = summary.sweep_count === 0;

  return (
    <div className="max-w-3xl flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900">Compliance</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Atomic Sweep — real-time tax withholding per Michigan Bulletin 2026-03-BT
        </p>
      </div>

      {/* W-2G alert */}
      {summary.w2g_threshold_reached && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 flex items-start gap-3">
          <span className="text-amber-500 text-lg leading-none mt-0.5">⚠</span>
          <div>
            <p className="text-sm font-semibold text-amber-800">W-2G Reporting Threshold Reached</p>
            <p className="text-xs text-amber-700 mt-0.5">
              YTD gross exceeds $600. IRS Form W-2G reporting applies. Consult your tax advisor.
            </p>
          </div>
        </div>
      )}

      {/* YTD summary cards */}
      <div>
        <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide mb-3">Year-to-Date</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Gross Earned" value={fmt(summary.ytd_gross)} sub={`${summary.sweep_count} sweep${summary.sweep_count !== 1 ? "s" : ""}`} />
          <StatCard label="Total Withheld" value={fmt(summary.ytd_withheld)} sub={`Effective rate: ${pct(summary.ytd_withheld / Math.max(summary.ytd_gross, 1))}`} />
          <StatCard label="Net Credited" value={fmt(summary.ytd_net)} highlight />
          <StatCard label="W-2G Status" value={summary.w2g_threshold_reached ? "Triggered" : "Below threshold"} sub="$600 IRS threshold" />
        </div>
      </div>

      {/* Jurisdiction breakdown */}
      <div>
        <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide mb-3">Withholding by Jurisdiction</h2>
        <div className="bg-white rounded-xl border border-zinc-200 divide-y divide-zinc-100">
          {[
            { label: "Michigan State Income Tax", rate: "4.25%", amount: summary.ytd_mi_state, color: "bg-blue-500" },
            { label: "Muskegon City Income Tax", rate: "1.00%", amount: summary.ytd_muskegon, color: "bg-indigo-500" },
            { label: "Federal Income Tax (Estimate)", rate: "22.00%", amount: summary.ytd_federal, color: "bg-violet-500" },
          ].map(({ label, rate, amount, color }) => {
            const barWidth = summary.ytd_gross > 0
              ? Math.round((amount / summary.ytd_gross) * 100)
              : 0;
            return (
              <div key={label} className="px-5 py-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="text-sm font-medium text-zinc-900">{label}</p>
                    <p className="text-xs text-zinc-400">{rate} statutory rate</p>
                  </div>
                  <p className="text-sm font-semibold text-zinc-900 tabular-nums">{fmt(amount)}</p>
                </div>
                <div className="h-1.5 bg-zinc-100 rounded-full overflow-hidden">
                  <div className={`h-full ${color} rounded-full`} style={{ width: `${barWidth}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Sweep history */}
      <div>
        <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide mb-3">Recent Sweeps</h2>
        <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden">
          {noActivity ? (
            <p className="px-5 py-16 text-center text-sm text-zinc-400">
              No sweeps yet. Revenue ingested via <code className="bg-zinc-100 px-1 rounded">/payments/ingest</code> will appear here.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-100">
                  {["Date", "Source", "Gross", "Withheld", "Net", "Status"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.map((r) => {
                  const withheld = r.mi_state_withholding + r.muskegon_city_withholding + r.federal_withholding;
                  return (
                    <tr key={r.id} className="border-b border-zinc-50 last:border-0 hover:bg-zinc-50">
                      <td className="px-4 py-3 text-zinc-500 tabular-nums">
                        {new Date(r.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                      </td>
                      <td className="px-4 py-3 text-zinc-600">
                        {SOURCE_LABELS[r.source] ?? r.source}
                      </td>
                      <td className="px-4 py-3 text-zinc-900 tabular-nums font-medium">{fmt(r.gross_amount)}</td>
                      <td className="px-4 py-3 text-red-600 tabular-nums">−{fmt(withheld)}</td>
                      <td className="px-4 py-3 text-green-700 tabular-nums font-semibold">{fmt(r.net_amount)}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                          r.sweep_status === "completed"
                            ? "bg-green-100 text-green-700"
                            : r.sweep_status === "failed"
                            ? "bg-red-100 text-red-700"
                            : "bg-yellow-100 text-yellow-700"
                        }`}>
                          {r.sweep_status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
