import { createAdminClient } from "@/lib/supabase/admin";

export default async function AdminOverviewPage() {
  const supabase = createAdminClient();

  const [{ data: loans }, { data: merchants }] = await Promise.all([
    supabase.from("loans").select("status, amount_inr, trust_score"),
    supabase.from("merchants").select("id, kyc_status"),
  ]);

  const total = loans?.length ?? 0;
  const pendingReview = loans?.filter((l) => l.status === "pending" && l.trust_score !== null).length ?? 0;
  const disbursed = loans?.filter((l) => l.status === "disbursed").length ?? 0;
  const totalDisbursed = loans
    ?.filter((l) => ["disbursed", "repaid"].includes(l.status))
    .reduce((sum, l) => sum + Number(l.amount_inr), 0) ?? 0;
  const repaid = loans?.filter((l) => l.status === "repaid").length ?? 0;
  const totalMerchants = merchants?.length ?? 0;
  const verifiedMerchants = merchants?.filter((m) => m.kyc_status === "verified").length ?? 0;
  const kycUnderReview = merchants?.filter((m) => m.kyc_status === "under_review").length ?? 0;

  const stats = [
    { label: "Total Loans", value: total },
    { label: "Loans Pending Review", value: pendingReview, highlight: pendingReview > 0, color: "yellow" },
    { label: "KYC Under Review", value: kycUnderReview, highlight: kycUnderReview > 0, color: "blue" },
    { label: "Disbursed", value: disbursed },
    { label: "Repaid", value: repaid },
    { label: "Total Disbursed", value: `₹${totalDisbursed.toLocaleString("en-IN")}` },
    { label: "Merchants", value: `${verifiedMerchants} / ${totalMerchants} verified` },
  ];

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-zinc-900">Admin Overview</h1>
        <p className="text-sm text-zinc-500 mt-1">Platform-wide stats</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {stats.map(({ label, value, highlight, color }) => {
          const borderClass = highlight
            ? color === "blue" ? "border-blue-300 bg-blue-50" : "border-yellow-300 bg-yellow-50"
            : "border-zinc-200";
          const textClass = highlight
            ? color === "blue" ? "text-blue-700" : "text-yellow-700"
            : "text-zinc-900";
          return (
            <div key={label} className={`bg-white rounded-xl border p-5 ${borderClass}`}>
              <p className="text-xs font-medium text-zinc-500 uppercase tracking-wide">{label}</p>
              <p className={`text-2xl font-semibold mt-1 ${textClass}`}>{value}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
