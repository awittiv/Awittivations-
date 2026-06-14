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
