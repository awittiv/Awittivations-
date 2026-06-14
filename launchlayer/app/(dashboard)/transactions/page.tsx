import { createClient } from "@/lib/supabase/server";
import Link from "next/link";
import { redirect } from "next/navigation";

const POLYGONSCAN_TX = "https://amoy.polygonscan.com/tx";

export default async function TransactionsPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: merchant } = await supabase
    .from("merchants")
    .select("id")
    .eq("user_id", user.id)
    .single();

  const loanIds =
    merchant?.id
      ? (
          await supabase
            .from("loans")
            .select("id")
            .eq("merchant_id", merchant.id)
        ).data?.map((l) => l.id) ?? []
      : [];

  const { data: transactions } = loanIds.length
    ? await supabase
        .from("transactions")
        .select("*, loans(purpose)")
        .in("loan_id", loanIds)
        .order("created_at", { ascending: false })
    : { data: [] };

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-zinc-900">Transactions</h1>
        <p className="text-sm text-zinc-500 mt-1">All disbursements and repayments</p>
      </div>

      <div className="bg-white rounded-xl border border-zinc-200">
        {!transactions || transactions.length === 0 ? (
          <div className="px-5 py-16 text-center">
            <p className="text-sm text-zinc-400">No transactions yet.</p>
            <p className="text-xs text-zinc-400 mt-1">
              Transactions appear here once a loan is disbursed or repaid.
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100">
                <th className="px-5 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">Loan</th>
                <th className="px-5 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">Type</th>
                <th className="px-5 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">Amount</th>
                <th className="px-5 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">Polygon TX</th>
                <th className="px-5 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">Date</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx) => (
                <tr key={tx.id} className="border-b border-zinc-50 last:border-0 hover:bg-zinc-50">
                  <td className="px-5 py-3 text-zinc-700">
                    {(tx.loans as { purpose: string } | null)?.purpose ?? "—"}
                  </td>
                  <td className="px-5 py-3">
                    <span
                      className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium capitalize ${
                        tx.type === "disburse"
                          ? "bg-green-100 text-green-800"
                          : "bg-zinc-100 text-zinc-600"
                      }`}
                    >
                      {tx.type}
                    </span>
                  </td>
                  <td
                    className={`px-5 py-3 font-medium ${
                      tx.type === "disburse" ? "text-green-600" : "text-zinc-700"
                    }`}
                  >
                    {tx.type === "disburse" ? "+" : "-"}₹
                    {Number(tx.amount).toLocaleString("en-IN")}
                  </td>
                  <td className="px-5 py-3 font-mono text-xs">
                    {tx.polygon_tx_hash ? (
                      <Link
                        href={`${POLYGONSCAN_TX}/${tx.polygon_tx_hash}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline"
                        title={tx.polygon_tx_hash}
                      >
                        {tx.polygon_tx_hash.slice(0, 10)}…{tx.polygon_tx_hash.slice(-6)}
                      </Link>
                    ) : (
                      <span className="text-zinc-400">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-zinc-400">
                    {new Date(tx.created_at).toLocaleDateString("en-IN")}
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
