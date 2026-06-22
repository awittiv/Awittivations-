"use client";

import { useEffect, useState, useCallback } from "react";
import { createClient } from "@/lib/supabase/client";
import KycUpload from "@/components/KycUpload";

type KycStatus = "pending" | "under_review" | "verified" | "rejected";

const kycColors: Record<KycStatus, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  under_review: "bg-blue-100 text-blue-800",
  verified: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
};

const kycLabels: Record<KycStatus, string> = {
  pending: "Not submitted",
  under_review: "Under review",
  verified: "Verified",
  rejected: "Rejected",
};

export default function SettingsPage() {
  const [merchantId, setMerchantId] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [phone, setPhone] = useState("");
  const [walletAddress, setWalletAddress] = useState("");
  const [kycStatus, setKycStatus] = useState<KycStatus>("pending");
  const [submittedDocs, setSubmittedDocs] = useState<Array<"aadhaar" | "pan" | "gst">>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const loadMerchant = useCallback(async () => {
    const supabase = createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return;

    const { data: merchant } = await supabase
      .from("merchants")
      .select("*")
      .eq("user_id", user.id)
      .single();

    if (merchant) {
      setMerchantId(merchant.id);
      setBusinessName(merchant.business_name ?? "");
      setPhone(merchant.phone ?? "");
      setWalletAddress(merchant.wallet_address ?? "");
      setKycStatus((merchant.kyc_status as KycStatus) ?? "pending");

      const { data: docs } = await supabase
        .from("kyc_documents")
        .select("doc_type")
        .eq("merchant_id", merchant.id);

      setSubmittedDocs((docs ?? []).map((d: { doc_type: "aadhaar" | "pan" | "gst" }) => d.doc_type));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadMerchant();
  }, [loadMerchant]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setMessage("");

    if (walletAddress && !/^0x[a-fA-F0-9]{40}$/.test(walletAddress)) {
      setMessage("Wallet address must be a valid Polygon/Ethereum address (0x followed by 40 hex characters).");
      return;
    }

    setSaving(true);
    const supabase = createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return;
    const { error } = await supabase
      .from("merchants")
      .update({ business_name: businessName, phone, wallet_address: walletAddress || null })
      .eq("user_id", user.id);
    setSaving(false);
    setMessage(error ? error.message : "Saved successfully.");
  }

  if (loading) return <div className="text-sm text-zinc-400">Loading...</div>;

  return (
    <div className="max-w-lg flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900">Settings</h1>
        <p className="text-sm text-zinc-500 mt-1">Manage your merchant profile</p>
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 p-6">
        <form onSubmit={handleSave} className="flex flex-col gap-5">
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">Business name</label>
            <input
              type="text"
              required
              value={businessName}
              onChange={(e) => setBusinessName(e.target.value)}
              className="w-full px-3 py-2 border border-zinc-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">Phone (WhatsApp)</label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full px-3 py-2 border border-zinc-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900"
              placeholder="+91 98765 43210"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">Polygon wallet address</label>
            <input
              type="text"
              value={walletAddress}
              onChange={(e) => setWalletAddress(e.target.value)}
              className="w-full px-3 py-2 border border-zinc-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900 font-mono"
              placeholder="0x..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">KYC Status</label>
            <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${kycColors[kycStatus]}`}>
              {kycLabels[kycStatus]}
            </span>
            {kycStatus === "rejected" && (
              <p className="text-xs text-red-600 mt-1">
                Your documents were rejected. Please re-upload corrected files below.
              </p>
            )}
          </div>

          {message && (
            <p className={`text-sm ${message.includes("error") || message.includes("Error") ? "text-red-600" : "text-green-600"}`}>
              {message}
            </p>
          )}

          <button
            type="submit"
            disabled={saving}
            className="bg-zinc-900 text-white py-2 rounded-lg text-sm font-medium hover:bg-zinc-800 disabled:opacity-50 transition-colors"
          >
            {saving ? "Saving..." : "Save changes"}
          </button>
        </form>
      </div>

      {merchantId && (
        <KycUpload
          merchantId={merchantId}
          submittedDocs={submittedDocs}
          onDocUploaded={loadMerchant}
        />
      )}
    </div>
  );
}
