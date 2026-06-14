import { createAdminClient } from "@/lib/supabase/admin";
import AdminLoanActions from "@/components/AdminLoanActions";

const statusColors: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  approved: "bg-blue-100 text-blue-800",
  disbursed: "bg-green-100 text-green-800",
  repaid: "bg-zinc-100 text-zinc-600",
  rejected: "bg-red-100 text-red-800",
};

export default async function AdminLoansPage() {
  const supabase = createAdminClient();
  const { data: loans } = await supabase
    .from("loans")
    .select("*, merchants(business_name, phone, wallet_address)")
    .order("created_at", { ascending: false });

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-zinc-900">All Loans</h1>
        <p className="text-sm text-zinc-500 mt-1">{loans?.length ?? 0} total across all merchants</p>
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden">
        {!loans || loans.length === 0 ? (
          <p className="px-5 py-16 text-center text-sm text-zinc-400">No loans yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100">
                {["Merchant", "Purpose", "Amount", "Score", "Status", "Date", "Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loans.map((loan) => (
                <tr key={loan.id} className="border-b border-zinc-50 last:border-0 hover:bg-zinc-50">
                  <td className="px-4 py-3 text-zinc-900 font-medium">
                    {(loan.merchants as { business_name: string } | null)?.business_name ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-zinc-700 max-w-[160px] truncate">{loan.purpose}</td>
                  <td className="px-4 py-3 text-zinc-700 font-medium">₹{Number(loan.amount_inr).toLocaleString("en-IN")}</td>
                  <td className="px-4 py-3 text-zinc-600">{loan.trust_score ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[loan.status] ?? ""}`}>
                      {loan.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-zinc-400">{new Date(loan.created_at).toLocaleDateString("en-IN")}</td>
                  <td className="px-4 py-3">
                    <AdminLoanActions loanId={loan.id} status={loan.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
