import { createClient } from "@/lib/supabase/client";

const BASE_URL = process.env.NEXT_PUBLIC_BANKIT_API_URL ?? "http://localhost:8000";

async function getAuthHeader(): Promise<Record<string, string>> {
  const supabase = createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) return {};
  return { Authorization: `Bearer ${session.access_token}` };
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = await getAuthHeader();
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...headers, ...options.headers },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const bankitApi = {
  payments: {
    sweepSummary: () => apiFetch<SweepSummary>("/payments/sweep-summary"),
    sweepHistory: () => apiFetch<SweepRecord[]>("/payments/sweep-history"),
    ingest: (data: { gross_amount: number; source: string; reference_id?: string }) =>
      apiFetch("/payments/ingest", { method: "POST", body: JSON.stringify(data) }),
  },
  loans: {
    list: () => apiFetch<LoanResponse[]>("/loans"),
    get: (id: string) => apiFetch<LoanResponse>(`/loans/${id}`),
    create: (data: CreateLoanRequest) =>
      apiFetch<LoanResponse>("/loans", { method: "POST", body: JSON.stringify(data) }),
    repay: (id: string) =>
      apiFetch<LoanResponse>(`/loans/${id}/repay`, { method: "POST" }),
  },
  merchants: {
    get: (id: string) => apiFetch<MerchantResponse>(`/merchants/${id}`),
    submitKycDoc: (id: string, data: KycDocSubmit) =>
      apiFetch(`/merchants/${id}/kyc/submit`, { method: "POST", body: JSON.stringify(data) }),
    listKycDocs: (id: string) =>
      apiFetch<KycDocument[]>(`/merchants/${id}/kyc/documents`),
  },
  admin: {
    loans: {
      list: () => apiFetch<AdminLoan[]>("/admin/loans"),
      approve: (id: string) => apiFetch<LoanResponse>(`/admin/loans/${id}/approve`, { method: "POST" }),
      reject: (id: string) => apiFetch<LoanResponse>(`/admin/loans/${id}/reject`, { method: "POST" }),
      disburse: (id: string) => apiFetch<LoanResponse>(`/admin/loans/${id}/disburse`, { method: "POST" }),
    },
    merchants: {
      list: () => apiFetch<MerchantResponse[]>("/admin/merchants"),
      updateKyc: (id: string, status: string) =>
        apiFetch(`/admin/merchants/${id}/kyc`, { method: "PATCH", body: JSON.stringify({ status }) }),
    },
  },
};

export interface LoanResponse {
  id: string;
  merchant_id: string;
  amount_inr: number;
  purpose: string;
  status: "pending" | "approved" | "disbursed" | "repaid" | "rejected";
  trust_score: number | null;
  tx_hash: string | null;
  created_at: string;
}

export interface CreateLoanRequest {
  amount_inr: number;
  purpose: string;
}

export interface MerchantResponse {
  id: string;
  user_id: string;
  business_name: string;
  phone: string | null;
  wallet_address: string | null;
  kyc_status: string;
  created_at: string;
}

export interface AdminLoan extends LoanResponse {
  merchants: {
    business_name: string;
    phone: string | null;
    wallet_address: string | null;
  } | null;
}

export interface SweepSummary {
  ytd_gross: number;
  ytd_withheld: number;
  ytd_net: number;
  ytd_mi_state: number;
  ytd_muskegon: number;
  ytd_federal: number;
  w2g_threshold_reached: boolean;
  sweep_count: number;
}

export interface SweepRecord {
  id: string;
  merchant_id: string;
  gross_amount: number;
  mi_state_withholding: number;
  muskegon_city_withholding: number;
  federal_withholding: number;
  net_amount: number;
  source: string;
  reference_id: string | null;
  sweep_status: string;
  tx_hash: string | null;
  created_at: string;
}

export interface KycDocSubmit {
  doc_type: "aadhaar" | "pan" | "gst";
  storage_path: string;
  file_name: string;
}

export interface KycDocument {
  id: string;
  merchant_id: string;
  doc_type: "aadhaar" | "pan" | "gst";
  storage_path: string;
  file_name: string;
  signed_url: string;
  created_at: string;
}
