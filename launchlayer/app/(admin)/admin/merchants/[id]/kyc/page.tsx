import Link from "next/link";
import { notFound } from "next/navigation";
import { createAdminClient } from "@/lib/supabase/admin";
import AdminKycSelect from "@/components/AdminKycSelect";

const DOC_LABELS: Record<string, string> = {
  aadhaar: "Aadhaar Card",
  pan: "PAN Card",
  gst: "GST Certificate",
};

export default async function MerchantKycPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = createAdminClient();

  const { data: merchant } = await supabase
    .from("merchants")
    .select("*")
    .eq("id", id)
    .single();

  if (!merchant) notFound();

  const { data: docs } = await supabase
    .from("kyc_documents")
    .select("*")
    .eq("merchant_id", id)
    .order("created_at", { ascending: true });

  const docsWithUrls = await Promise.all(
    (docs ?? []).map(async (doc: { id: string; doc_type: string; storage_path: string; file_name: string; created_at: string }) => {
      const { data } = await supabase.storage
        .from("kyc-docs")
        .createSignedUrl(doc.storage_path, 3600);
      return { ...doc, signed_url: data?.signedUrl ?? "" };
    })
  );

  const submitted = new Set(docsWithUrls.map((d) => d.doc_type));

  return (
    <div className="max-w-2xl">
      <div className="mb-6 flex items-center gap-3">
        <Link href="/admin/merchants" className="text-sm text-zinc-400 hover:text-zinc-700">
          ← Merchants
        </Link>
      </div>

      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-zinc-900">{merchant.business_name}</h1>
        <p className="text-sm text-zinc-500 mt-1">KYC document review</p>
      </div>

      <div className="bg-white rounded-xl border border-zinc-200 p-5 mb-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-zinc-400 uppercase tracking-wide font-medium mb-1">KYC Status</p>
            <AdminKycSelect merchantId={merchant.id} current={merchant.kyc_status ?? "pending"} />
          </div>
          <div className="text-right">
            <p className="text-xs text-zinc-400 uppercase tracking-wide font-medium mb-1">Documents</p>
            <p className="text-sm font-medium text-zinc-900">{docsWithUrls.length} / 3 submitted</p>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {["aadhaar", "pan", "gst"].map((docType) => {
          const doc = docsWithUrls.find((d) => d.doc_type === docType);
          return (
            <div
              key={docType}
              className={`flex items-center justify-between p-4 rounded-lg border ${
                submitted.has(docType) ? "border-zinc-200 bg-white" : "border-zinc-100 bg-zinc-50"
              }`}
            >
              <div>
                <p className="text-sm font-medium text-zinc-900">{DOC_LABELS[docType]}</p>
                {doc ? (
                  <p className="text-xs text-zinc-400 mt-0.5">
                    {doc.file_name} · {new Date(doc.created_at).toLocaleDateString("en-IN")}
                  </p>
                ) : (
                  <p className="text-xs text-zinc-400 mt-0.5">Not submitted</p>
                )}
              </div>
              <div className="shrink-0 ml-4">
                {doc?.signed_url ? (
                  <a
                    href={doc.signed_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs font-medium text-blue-600 hover:text-blue-800 underline"
                  >
                    View
                  </a>
                ) : (
                  <span className="text-xs text-zinc-300">—</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {docsWithUrls.length === 3 && merchant.kyc_status === "under_review" && (
        <div className="mt-5 p-4 rounded-lg bg-blue-50 border border-blue-200">
          <p className="text-sm font-medium text-blue-800">All documents submitted.</p>
          <p className="text-xs text-blue-600 mt-0.5">
            Review each document above, then set KYC Status to <strong>verified</strong> or <strong>rejected</strong>.
          </p>
        </div>
      )}
    </div>
  );
}
