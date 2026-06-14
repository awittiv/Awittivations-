"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { bankitApi } from "@/lib/api";

type Status = "pending" | "approved" | "disbursed" | "repaid" | "rejected";

export default function AdminLoanActions({ loanId, status }: { loanId: string; status: Status }) {
  const router = useRouter();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function act(action: "approve" | "reject" | "disburse") {
    setLoading(action);
    setError("");
    try {
      await bankitApi.admin.loans[action](loanId);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setLoading(null);
    }
  }

  const canApprove = status === "pending";
  const canReject = status === "pending" || status === "approved";
  const canDisburse = status === "approved";

  if (!canApprove && !canReject && !canDisburse) return null;

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex gap-1.5">
        {canApprove && (
          <button
            onClick={() => act("approve")}
            disabled={!!loading}
            className="px-3 py-1 text-xs rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading === "approve" ? "…" : "Approve"}
          </button>
        )}
        {canDisburse && (
          <button
            onClick={() => act("disburse")}
            disabled={!!loading}
            className="px-3 py-1 text-xs rounded-md bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
          >
            {loading === "disburse" ? "…" : "Disburse"}
          </button>
        )}
        {canReject && (
          <button
            onClick={() => act("reject")}
            disabled={!!loading}
            className="px-3 py-1 text-xs rounded-md bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
          >
            {loading === "reject" ? "…" : "Reject"}
          </button>
        )}
      </div>
      {error && <p className="text-xs text-red-500 max-w-[180px] text-right">{error}</p>}
    </div>
  );
}
