"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { bankitApi } from "@/lib/api";

type KycStatus = "pending" | "under_review" | "verified" | "rejected";

const colors: Record<KycStatus, string> = {
  pending: "text-yellow-700 bg-yellow-50 border-yellow-200",
  under_review: "text-blue-700 bg-blue-50 border-blue-200",
  verified: "text-green-700 bg-green-50 border-green-200",
  rejected: "text-red-700 bg-red-50 border-red-200",
};

export default function AdminKycSelect({ merchantId, current }: { merchantId: string; current: KycStatus }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const status = e.target.value as KycStatus;
    setLoading(true);
    try {
      await bankitApi.admin.merchants.updateKyc(merchantId, status);
      router.refresh();
    } finally {
      setLoading(false);
    }
  }

  return (
    <select
      defaultValue={current}
      onChange={handleChange}
      disabled={loading}
      className={`text-xs font-medium px-2 py-1 rounded border cursor-pointer disabled:opacity-50 ${colors[current] ?? colors.pending}`}
    >
      <option value="pending">pending</option>
      <option value="under_review">under review</option>
      <option value="verified">verified</option>
      <option value="rejected">rejected</option>
    </select>
  );
}
