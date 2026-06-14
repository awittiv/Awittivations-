import Link from "next/link";
import { createAdminClient } from "@/lib/supabase/admin";
import { notFound } from "next/navigation";
import AdminKycSelect from "@/components/AdminKycSelect";

type KycStatus = "pending" | "under_review" | "verified" | "rejected";

const statusColors: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  approved: "bg-blue-100 text-blue-800",
  disbursed: "bg-green-100 text-green-800",
  repaid: "bg-zinc-100 text-zinc-600",
  rejected: "bg-red-100 text-red-800",
};

const kycColors: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  under_review: "bg-blue-100 text-blue-800",
  verified: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
};

export default async function AdminMerchantDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = createAdminClient();

  const [{ data: merchant }, { data: loans }, { data: kycDocs }] = await Promise.all([
    supabase.from("merchants").select("*").eq("id", id).single(),
    supabase
      .from("loans")
      .select("*")
      .eq("merchant_id", id)
      .order("created_at", { ascending: false }),
    supabase.from("kyc_documents").select("*").eq("merchant_id", id),
  ]);

  if (!merchant) notFound();

  const kyc = (merchant.kyc_status ?? "pending") as KycStatus;
  const totalDisbursed =
    loans
      ?.filter((l) => ["disbursed", "repaid"].includes(l.status))
      .reduce((s, l) => s + Number(l.amount_inr), 0) ?? 0;

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3 mb-8">
        <Link href="/admin/merchants" className="text-sm text-zinc-500 hover:text-zinc-900">
          ← Merchants
        </Link>
        <span className="text-zinc-300">/</span>
        <h1 className="text-xl font-semibold text-zinc-900">{merchant.business_name}</h1>
      </div>

      {/* Profile card */}
      <div className="bg-white rounded-xl border border-zinc-200 p-6 mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1">Merchant</p>
            <p className="text-lg font-semibold text-zinc-900">{merchant.business_name}</p>
          </div>
          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${kycColors[kyc]}`}>
            KYC: {kyc}
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
          <div>
            <dt className="text-zinc-400 text-xs">Phone</dt>
            <dd className="text-zinc-900">{merchant.phone ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-zinc-400 text-xs">Email</dt>
            <dd className="text-zinc-900">{merchant.email ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-zinc-400 text-xs">Wallet</dt>
            <dd className="text-zinc-900 font-mono text-xs break-all">
              {merchant.wallet_address ?? <span className="text-red-500 font-sans">Not set</span>}
            </dd>
          </div>
          <div>
            <dt className="text-zinc-400 text-xs">Joined</dt>
            <dd className="text-zinc-900">
              {new Date(merchant.created_at).toLocaleDateString("en-IN", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </dd>
          </div>
          <div>
            <dt className="text-zinc-400 text-xs">Total Disbursed</dt>
            <dd className="text-zinc-900 font-medium">₹{totalDisbursed.toLocaleString("en-IN")}</dd>
          </div>
          <div>
            <dt className="text-zinc-400 text-xs">Loans</dt>
            <dd className="text-zinc-900">{loans?.length ?? 0}</dd>
          </div>
        </dl>

        <div className="mt-5 pt-5 border-t border-zinc-100">
          <p className="text-xs font-medium text-zinc-500 mb-2">KYC Status</p>
          <AdminKycSelect merchantId={merchant.id} current={kyc} />
          {(kycDocs?.length ?? 0) > 0 && (
            <Link
              href={`/admin/merchants/${merchant.id}/kyc`}
              className="ml-3 text-xs text-blue-600 hover:underline"
            >
              Review docs ({kycDocs?.length}/3)
            </Link>
          )}
        </div>
      </div>

      {/* Loan history */}
      <div className="bg-white rounded-xl border border-zinc-200">
        <div className="px-5 py-4 border-b border-zinc-100">
          <h2 className="text-sm font-semibold text-zinc-900">Loan History</h2>
        </div>

        {!loans || loans.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-zinc-400">No loans yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100">
                {["Purpose", "Amount", "Score", "Status", "Date", "Error"].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loans.map((loan) => (
                <tr key={loan.id} className="border-b border-zinc-50 last:border-0 hover:bg-zinc-50">
                  <td className="px-4 py-3 text-zinc-900">{loan.purpose}</td>
                  <td className="px-4 py-3 text-zinc-700 font-medium">
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
                  <td className="px-4 py-3 text-zinc-400">
                    {new Date(loan.created_at).toLocaleDateString("en-IN")}
                  </td>
                  <td className="px-4 py-3 text-xs text-red-500 max-w-[160px] truncate">
                    {loan.error_reason ?? ""}
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
