import { createAdminClient } from "@/lib/supabase/admin";
import AdminLoanActions from "@/components/AdminLoanActions";
import Link from "next/link";

const POLYGONSCAN_TX = "https://amoy.polygonscan.com/tx";

const statusColors: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  approved: "bg-blue-100 text-blue-800",
  disbursed: "bg-green-100 text-green-800",
  repaid: "bg-zinc-100 text-zinc-600",
  rejected: "bg-red-100 text-red-800",
};

const STATUSES = ["all", "pending", "approved", "disbursed", "repaid", "rejected"] as const;
type StatusFilter = (typeof STATUSES)[number];

export default async function AdminLoansPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; page?: string }>;
}) {
  const { status: rawStatus, page: rawPage } = await searchParams;
  const statusFilter = (STATUSES.includes(rawStatus as StatusFilter) ? rawStatus : "all") as StatusFilter;
  const page = Math.max(1, parseInt(rawPage ?? "1") || 1);
  const pageSize = 50;

  const supabase = createAdminClient();
  let query = supabase
    .from("loans")
    .select("*, merchants(business_name, phone, wallet_address)", { count: "exact" })
    .order("created_at", { ascending: false })
    .range((page - 1) * pageSize, page * pageSize - 1);

  if (statusFilter !== "all") {
    query = query.eq("status", statusFilter);
  }

  const { data: loans, count } = await query;
  const totalPages = Math.ceil((count ?? 0) / pageSize);

  function pageUrl(p: number) {
    const params = new URLSearchParams();
    if (statusFilter !== "all") params.set("status", statusFilter);
    params.set("page", String(p));
    return `/admin/loans?${params}`;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900">All Loans</h1>
          <p className="text-sm text-zinc-500 mt-1">
            {count ?? 0} total · page {page} of {totalPages || 1}
          </p>
        </div>

        {/* Status filter */}
        <div className="flex gap-1.5 flex-wrap">
          {STATUSES.map((s) => (
            <Link
              key={s}
              href={s === "all" ? "/admin/loans" : `/admin/loans?status=${s}`}
              className={`px-3 py-1 rounded-lg text-xs font-medium border transition-colors ${
                statusFilter === s
                  ? "bg-zinc-900 text-white border-zinc-900"
                  : "bg-white text-zinc-600 border-zinc-200 hover:border-zinc-400"
              }`}
            >
              {s}
            </Link>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden">
        {!loans || loans.length === 0 ? (
          <p className="px-5 py-16 text-center text-sm text-zinc-400">No loans.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100">
                {["Merchant", "Purpose", "Amount", "Score", "Status", "TX", "Date", "Actions"].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide"
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {loans.map((loan) => (
                <>
                  <tr key={loan.id} className="border-b border-zinc-50 last:border-0 hover:bg-zinc-50">
                    <td className="px-4 py-3 text-zinc-900 font-medium">
                      {(loan.merchants as { business_name: string } | null)?.business_name ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-zinc-700 max-w-[140px] truncate" title={loan.purpose}>
                      {loan.purpose}
                    </td>
                    <td className="px-4 py-3 text-zinc-700 font-medium whitespace-nowrap">
                      ₹{Number(loan.amount_inr).toLocaleString("en-IN")}
                    </td>
                    <td className="px-4 py-3 text-zinc-600">{loan.trust_score ?? "—"}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                          statusColors[loan.status] ?? ""
                        }`}
                      >
                        {loan.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {loan.tx_hash ? (
                        <Link
                          href={`${POLYGONSCAN_TX}/${loan.tx_hash}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline"
                          title={loan.tx_hash}
                        >
                          {loan.tx_hash.slice(0, 8)}…
                        </Link>
                      ) : (
                        <span className="text-zinc-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-zinc-400 whitespace-nowrap">
                      {new Date(loan.created_at).toLocaleDateString("en-IN")}
                    </td>
                    <td className="px-4 py-3">
                      <AdminLoanActions loanId={loan.id} status={loan.status} />
                    </td>
                  </tr>
                  {loan.error_reason && (
                    <tr key={`${loan.id}-err`} className="border-b border-zinc-50 bg-red-50">
                      <td colSpan={8} className="px-4 py-1.5 text-xs text-red-600">
                        {loan.error_reason}
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-4">
          {page > 1 && (
            <Link href={pageUrl(page - 1)} className="px-3 py-1 text-sm border border-zinc-200 rounded-lg hover:bg-zinc-50">
              ← Prev
            </Link>
          )}
          <span className="px-3 py-1 text-sm text-zinc-500">
            {page} / {totalPages}
          </span>
          {page < totalPages && (
            <Link href={pageUrl(page + 1)} className="px-3 py-1 text-sm border border-zinc-200 rounded-lg hover:bg-zinc-50">
              Next →
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
