"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { bankitApi } from "@/lib/api";

export default function RepayButton({ loanId, amountInr }: { loanId: string; amountInr: number }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleRepay() {
    setLoading(true);
    setError("");
    try {
      await bankitApi.loans.repay(loanId);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Repayment failed. Please try again.");
      setConfirming(false);
    } finally {
      setLoading(false);
    }
  }

  if (confirming) {
    return (
      <div className="flex flex-col gap-2 items-end">
        <p className="text-sm text-zinc-600">
          Confirm repayment of <span className="font-semibold text-zinc-900">₹{amountInr.toLocaleString("en-IN")}</span>?
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => setConfirming(false)}
            disabled={loading}
            className="px-4 py-2 text-sm rounded-lg border border-zinc-200 text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleRepay}
            disabled={loading}
            className="px-4 py-2 text-sm rounded-lg bg-zinc-900 text-white hover:bg-zinc-700 disabled:opacity-50"
          >
            {loading ? "Processing…" : "Confirm Repayment"}
          </button>
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
      </div>
    );
  }

  return (
    <button
      onClick={() => setConfirming(true)}
      className="px-4 py-2 text-sm rounded-lg bg-zinc-900 text-white hover:bg-zinc-700"
    >
      Repay Loan
    </button>
  );
}
