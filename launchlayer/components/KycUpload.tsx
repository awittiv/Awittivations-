"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { bankitApi } from "@/lib/api";

const DOC_TYPES = [
  { key: "aadhaar" as const, label: "Aadhaar Card", hint: "Government-issued identity" },
  { key: "pan" as const, label: "PAN Card", hint: "Permanent Account Number" },
  { key: "gst" as const, label: "GST Certificate", hint: "GST registration proof" },
];

interface Props {
  merchantId: string;
  submittedDocs: Array<"aadhaar" | "pan" | "gst">;
  onDocUploaded: () => void;
}

export default function KycUpload({ merchantId, submittedDocs, onDocUploaded }: Props) {
  const [uploaded, setUploaded] = useState<Set<string>>(new Set(submittedDocs));
  const [uploading, setUploading] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function handleFile(docType: "aadhaar" | "pan" | "gst", file: File) {
    if (file.size > 5 * 1024 * 1024) {
      setErrors((p) => ({ ...p, [docType]: "File must be under 5 MB" }));
      return;
    }

    setUploading((p) => ({ ...p, [docType]: true }));
    setErrors((p) => ({ ...p, [docType]: "" }));

    try {
      const ext = file.name.split(".").pop() ?? "bin";
      const storagePath = `${merchantId}/${docType}_${Date.now()}.${ext}`;
      const supabase = createClient();

      const { error: uploadError } = await supabase.storage
        .from("kyc-docs")
        .upload(storagePath, file, { upsert: true });

      if (uploadError) throw new Error(uploadError.message);

      await bankitApi.merchants.submitKycDoc(merchantId, {
        doc_type: docType,
        storage_path: storagePath,
        file_name: file.name,
      });

      setUploaded((p) => new Set([...p, docType]));
      onDocUploaded();
    } catch (err: unknown) {
      setErrors((p) => ({ ...p, [docType]: (err as Error).message ?? "Upload failed" }));
    } finally {
      setUploading((p) => ({ ...p, [docType]: false }));
    }
  }

  const allDone = DOC_TYPES.every(({ key }) => uploaded.has(key));

  return (
    <div className="bg-white rounded-xl border border-zinc-200 p-6">
      <div className="mb-5">
        <h2 className="text-base font-semibold text-zinc-900">KYC Documents</h2>
        <p className="text-sm text-zinc-500 mt-0.5">
          Upload all three documents to unlock loan access.
        </p>
      </div>

      <div className="flex flex-col gap-3">
        {DOC_TYPES.map(({ key, label, hint }) => {
          const done = uploaded.has(key);
          const busy = uploading[key];
          const err = errors[key];

          return (
            <div
              key={key}
              className={`flex items-center justify-between p-4 rounded-lg border ${
                done ? "border-green-200 bg-green-50" : "border-zinc-200 bg-zinc-50"
              }`}
            >
              <div>
                <p className="text-sm font-medium text-zinc-900">{label}</p>
                <p className="text-xs text-zinc-400 mt-0.5">{hint}</p>
                {err && <p className="text-xs text-red-500 mt-1">{err}</p>}
              </div>
              <div className="shrink-0 ml-4">
                {done ? (
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    Uploaded
                  </span>
                ) : (
                  <label
                    className={`cursor-pointer inline-block text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
                      busy
                        ? "opacity-50 cursor-not-allowed bg-zinc-100 border-zinc-200 text-zinc-400"
                        : "bg-zinc-900 border-zinc-900 text-white hover:bg-zinc-800"
                    }`}
                  >
                    {busy ? "Uploading…" : "Upload"}
                    <input
                      type="file"
                      className="hidden"
                      disabled={busy}
                      accept="image/jpeg,image/png,image/webp,application/pdf"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) handleFile(key, f);
                        e.target.value = "";
                      }}
                    />
                  </label>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {allDone && (
        <div className="mt-4 p-3 rounded-lg bg-green-50 border border-green-200">
          <p className="text-sm font-medium text-green-700">
            All documents submitted — your account is under review.
          </p>
        </div>
      )}
    </div>
  );
}
