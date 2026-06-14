import { createAdminClient } from "@/lib/supabase/admin";
import AdminKycSelect from "@/components/AdminKycSelect";

export default async function AdminMerchantsPage() {
  const supabase = createAdminClient();
  const { data: merchants } = await supabase
    .from("merchants")
    .select("*")
    .order("created_at", { ascending: false });

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-zinc-900">Merchants</h1>
        <p className="text-sm text-zinc-500 mt-1">{merchants?.length ?? 0} registered</p>
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden">
        {!merchants || merchants.length === 0 ? (
          <p className="px-5 py-16 text-center text-sm text-zinc-400">No merchants yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100">
                {["Business", "Phone", "Wallet", "KYC Status", "Joined"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {merchants.map((m) => (
                <tr key={m.id} className="border-b border-zinc-50 last:border-0 hover:bg-zinc-50">
                  <td className="px-4 py-3 text-zinc-900 font-medium">{m.business_name}</td>
                  <td className="px-4 py-3 text-zinc-600">{m.phone ?? "—"}</td>
                  <td className="px-4 py-3 text-zinc-400 font-mono text-xs">
                    {m.wallet_address ? m.wallet_address.slice(0, 10) + "…" : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <AdminKycSelect merchantId={m.id} current={m.kyc_status ?? "pending"} />
                  </td>
                  <td className="px-4 py-3 text-zinc-400">{new Date(m.created_at).toLocaleDateString("en-IN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
