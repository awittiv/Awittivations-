import { createClient } from "@/lib/supabase/server";
import Link from "next/link";
import { redirect } from "next/navigation";

export default async function DashboardPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: merchant } = await supabase
    .from("merchants")
    .select("*")
    .eq("user_id", user.id)
    .single();

  const { data: loans } = await supabase
    .from("loans")
    .select("*")
    .eq("merchant_id", merchant?.id ?? "")
    .order("created_at", { ascending: false });

  const totalLoans = loans?.length ?? 0;
  const activeLoans = loans?.filter((l) => l.status === "disbursed").length ?? 0;
  const repaidLoans = loans?.filter((l) => l.status === "repaid").length ?? 0;
  const totalDisbursed = loans
    ?.filter((l) => ["disbursed", "repaid"].includes(l.status))
    .reduce((sum, l) => sum + Number(l.amount_inr), 0) ?? 0;

  const recentLoans = loans?.slice(0, 5) ?? [];

  const statusColors: Record<string, string> = {
    pending: "bg-yellow-100 text-yellow-800",
    approved: "bg-blue-100 text-blue-800",
    disbursed: "bg-green-100 text-green-800",
    repaid: "bg-zinc-100 text-zinc-600",
    rejected: "bg-red-100 text-red-800",
  };

  const walletMissing = !merchant?.wallet_address;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-zinc-900">
          Welcome, {merchant?.business_name ?? "Merchant"}
        </h1>
        <p className="text-sm text-zinc-500 mt-1">Here&apos;s your lending overview</p>
      </div>

      {walletMissing && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 mb-6">
          <p className="text-sm font-semibold text-amber-800">Wallet address required</p>
          <p className="text-xs text-amber-700 mt-1">
            Loan disbursements are sent to your Polygon wallet. Without one, approved loans
            won&apos;t be credited.{" "}
            <Link href="/settings" className="font-medium underline">
              Add wallet in Settings
            </Link>
          </p>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          { label: "Total Loans", value: totalLoans },
          { label: "Active (Disbursed)", value: activeLoans },
          { label: "Repaid", value: repaidLoans },
          { label: "Total Disbursed (₹)", value: `₹${totalDisbursed.toLocaleString("en-IN")}` },
        ].map((stat) => (
          <div key={stat.label} className="bg-white rounded-xl border border-zinc-200 p-5">
            <p className="text-xs text-zinc-500 uppercase tracking-wide">{stat.label}</p>
            <p className="text-2xl font-semibold text-zinc-900 mt-1">{stat.value}</p>
          </div>
        ))}
      </div>

      {/* Recent loans */}
      <div className="bg-white rounded-xl border border-zinc-200">
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-200">
          <h2 className="text-sm font-semibold text-zinc-900">Recent Loans</h2>
          <Link href="/loans/apply" className="text-xs font-medium text-zinc-900 bg-zinc-100 hover:bg-zinc-200 px-3 py-1.5 rounded-lg transition-colors">
            + Apply for loan
          </Link>
        </div>

        {recentLoans.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <p className="text-sm text-zinc-400">No loans yet.</p>
            <Link href="/loans/apply" className="text-sm text-zinc-900 font-medium hover:underline mt-1 inline-block">
              Apply for your first microloan
            </Link>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100">
                <th className="px-5 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">Purpose</th>
                <th className="px-5 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">Amount</th>
                <th className="px-5 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">Status</th>
                <th className="px-5 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">Date</th>
              </tr>
            </thead>
            <tbody>
              {recentLoans.map((loan) => (
                <tr key={loan.id} className="border-b border-zinc-50 last:border-0 hover:bg-zinc-50">
                  <td className="px-5 py-3 text-zinc-900">{loan.purpose}</td>
                  <td className="px-5 py-3 text-zinc-700 font-medium">₹{Number(loan.amount_inr).toLocaleString("en-IN")}</td>
                  <td className="px-5 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[loan.status] ?? ""}`}>
                      {loan.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-zinc-400">
                    {new Date(loan.created_at).toLocaleDateString("en-IN")}
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
