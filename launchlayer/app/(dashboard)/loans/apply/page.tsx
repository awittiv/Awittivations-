"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { bankitApi } from "@/lib/api";

type KycStatus = "pending" | "under_review" | "verified" | "rejected";

export default function ApplyLoanPage() {
  const router = useRouter();
  const [purpose, setPurpose] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [kycStatus, setKycStatus] = useState<KycStatus | null>(null);
  const [kycLoading, setKycLoading] = useState(true);

  useEffect(() => {
    async function loadKyc() {
      const supabase = createClient();
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;
      const { data: merchant } = await supabase
        .from("merchants")
        .select("kyc_status")
        .eq("user_id", user.id)
        .single();
      setKycStatus((merchant?.kyc_status as KycStatus) ?? "pending");
      setKycLoading(false);
    }
    loadKyc();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (kycStatus !== "verified") return;
    setLoading(true);
    setError("");

    try {
      const loan = await bankitApi.loans.create({
        amount_inr: parseFloat(amount),
        purpose,
      });
      router.push(`/loans/${loan.id}`);
      router.refresh();
    } catch (err: unknown) {
      setError((err as Error).message ?? "Submission failed");
      setLoading(false);
    }
  }

  if (kycLoading) return <div className="text-sm text-zinc-400">Loading...</div>;

  const kycBlocked = kycStatus !== "verified";

  return (
    <div className="max-w-lg">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-zinc-900">Apply for a Microloan</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Our AI scores your trust profile and disburses funds via Polygon.
        </p>
      </div>

      {/* KYC gate banner */}
      {kycBlocked && (
        <div className={`rounded-xl border px-5 py-4 mb-6 ${
          kycStatus === "rejected"
            ? "border-red-200 bg-red-50"
            : "border-amber-200 bg-amber-50"
        }`}>
          <p className={`text-sm font-semibold ${kycStatus === "rejected" ? "text-red-800" : "text-amber-800"}`}>
            {kycStatus === "pending" && "KYC documents required"}
            {kycStatus === "under_review" && "KYC under review"}
            {kycStatus === "rejected" && "KYC rejected — re-upload required"}
          </p>
          <p className={`text-xs mt-1 ${kycStatus === "rejected" ? "text-red-600" : "text-amber-700"}`}>
            {kycStatus === "pending" && "Upload your Aadhaar, PAN, and GST certificate in Settings before applying."}
            {kycStatus === "under_review" && "Your documents are being reviewed. Loan applications open once KYC is verified."}
            {kycStatus === "rejected" && "Your documents were rejected. Please re-upload corrected files in Settings."}
          </p>
          <Link
            href="/settings"
            className="inline-block mt-2 text-xs font-medium text-zinc-900 underline"
          >
            Go to Settings →
          </Link>
        </div>
      )}

      <div className={`bg-white rounded-xl border border-zinc-200 p-6 ${kycBlocked ? "opacity-50 pointer-events-none select-none" : ""}`}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">Loan purpose</label>
            <input
              type="text"
              required
              disabled={kycBlocked}
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="e.g. Rice inventory for the season"
              className="w-full px-3 py-2 border border-zinc-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900 disabled:bg-zinc-50"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">Amount (₹ INR)</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 text-sm">₹</span>
              <input
                type="number"
                required
                min={100}
                max={100000}
                disabled={kycBlocked}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="5000"
                className="w-full pl-7 pr-3 py-2 border border-zinc-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900 disabled:bg-zinc-50"
              />
            </div>
            <p className="text-xs text-zinc-400 mt-1">Min ₹100 · Max ₹1,00,000</p>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={loading || kycBlocked}
            className="w-full bg-zinc-900 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-zinc-800 disabled:opacity-50 transition-colors"
          >
            {loading ? "Submitting…" : "Submit application"}
          </button>
        </form>
      </div>

      {!kycBlocked && (
        <p className="text-xs text-zinc-400 mt-4 text-center">
          Applications are scored in seconds via AI + TPAP corridor intelligence.
        </p>
      )}
    </div>
  );
}
