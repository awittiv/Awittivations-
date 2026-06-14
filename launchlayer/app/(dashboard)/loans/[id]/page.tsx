import { createClient } from "@/lib/supabase/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import RepayButton from "@/components/RepayButton";

const statusColors: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  approved: "bg-blue-100 text-blue-800",
  disbursed: "bg-green-100 text-green-800",
  repaid: "bg-zinc-100 text-zinc-600",
  rejected: "bg-red-100 text-red-800",
};

export default async function LoanDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  const { data: merchant } = await supabase
    .from("merchants")
    .select("id")
    .eq("user_id", user!.id)
    .single();

  const { data: loan } = await supabase
    .from("loans")
    .select("*")
    .eq("id", id)
    .eq("merchant_id", merchant?.id ?? "")
    .single();

  if (!loan) notFound();

  const { data: messages } = await supabase
    .from("loan_messages")
    .select("*")
    .eq("loan_id", id)
    .order("created_at", { ascending: true });

  const { data: transactions } = await supabase
    .from("transactions")
    .select("*")
    .eq("loan_id", id)
    .order("created_at", { ascending: false });

  return (
    <div>
      <div className="mb-6">
        <Link href="/loans" className="text-sm text-zinc-400 hover:text-zinc-700">← Loans</Link>
      </div>

      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900">{loan.purpose}</h1>
          <p className="text-sm text-zinc-500 mt-1">
            ₹{Number(loan.amount_inr).toLocaleString("en-IN")} &middot; Applied {new Date(loan.created_at).toLocaleDateString("en-IN")}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`inline-flex px-3 py-1 rounded-full text-sm font-medium ${statusColors[loan.status] ?? ""}`}>
            {loan.status}
          </span>
          {loan.status === "disbursed" && (
            <RepayButton loanId={loan.id} amountInr={Number(loan.amount_inr)} />
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Loan details */}
        <div className="bg-white rounded-xl border border-zinc-200 p-5">
          <h2 className="text-sm font-semibold text-zinc-900 mb-4">Loan Details</h2>
          <dl className="flex flex-col gap-3">
            {[
              { label: "Amount", value: `₹${Number(loan.amount_inr).toLocaleString("en-IN")}` },
              { label: "Trust Score", value: loan.trust_score ? `${loan.trust_score}/100` : "Pending" },
              { label: "Blockchain TX", value: loan.tx_hash ? loan.tx_hash.slice(0, 20) + "..." : "—" },
            ].map(({ label, value }) => (
              <div key={label} className="flex justify-between text-sm">
                <dt className="text-zinc-500">{label}</dt>
                <dd className="text-zinc-900 font-medium font-mono">{value}</dd>
              </div>
            ))}
          </dl>
        </div>

        {/* Transactions */}
        <div className="bg-white rounded-xl border border-zinc-200 p-5">
          <h2 className="text-sm font-semibold text-zinc-900 mb-4">Transactions</h2>
          {!transactions || transactions.length === 0 ? (
            <p className="text-sm text-zinc-400">No transactions yet.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {transactions.map((tx) => (
                <div key={tx.id} className="flex justify-between text-sm">
                  <span className={`font-medium ${tx.type === "disburse" ? "text-green-600" : "text-zinc-700"}`}>
                    {tx.type === "disburse" ? "+" : "-"}₹{Number(tx.amount).toLocaleString("en-IN")}
                    <span className="ml-2 text-xs text-zinc-400 capitalize">{tx.type}</span>
                  </span>
                  <span className="text-zinc-400">{new Date(tx.created_at).toLocaleDateString("en-IN")}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* WhatsApp message thread */}
      {messages && messages.length > 0 && (
        <div className="mt-6 bg-white rounded-xl border border-zinc-200 p-5">
          <h2 className="text-sm font-semibold text-zinc-900 mb-4">WhatsApp Thread</h2>
          <div className="flex flex-col gap-3">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`max-w-sm px-4 py-2.5 rounded-2xl text-sm ${
                  msg.direction === "inbound"
                    ? "bg-zinc-100 text-zinc-800 self-start rounded-tl-sm"
                    : "bg-green-500 text-white self-end rounded-tr-sm ml-auto"
                }`}
              >
                {msg.content}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
