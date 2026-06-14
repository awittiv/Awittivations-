"use client";

import { useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

export default function SignupPage() {
  const [businessName, setBusinessName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    // E.164 validation — required for WhatsApp routing
    if (!/^\+[1-9]\d{7,14}$/.test(phone.replace(/\s/g, ""))) {
      setError("Phone must be in international format, e.g. +91 98765 43210");
      return;
    }

    setLoading(true);
    const supabase = createClient();

    const { data, error: signUpError } = await supabase.auth.signUp({ email, password });

    if (signUpError) {
      setError(signUpError.message);
      setLoading(false);
      return;
    }

    if (data.user) {
      // Upsert so a retry after partial failure doesn't create a duplicate row
      const { error: merchantError } = await supabase.from("merchants").upsert(
        { user_id: data.user.id, business_name: businessName, phone: phone.replace(/\s/g, "") },
        { onConflict: "user_id" }
      );

      if (merchantError) {
        setError(merchantError.message);
        setLoading(false);
        return;
      }
    }

    // Supabase may require email confirmation before issuing a session
    if (!data.session) {
      setConfirmed(true);
      setLoading(false);
      return;
    }

    // Session already active — go straight to dashboard
    window.location.href = "/loans";
  }

  if (confirmed) {
    return (
      <>
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-zinc-900">Check your email</h1>
          <p className="text-sm text-zinc-500 mt-1">
            We sent a confirmation link to <strong>{email}</strong>.
            Click it to activate your account and sign in.
          </p>
        </div>
        <p className="text-sm text-zinc-500 text-center">
          <Link href="/login" className="text-zinc-900 font-medium hover:underline">
            Back to sign in
          </Link>
        </p>
      </>
    );
  }

  return (
    <>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-zinc-900">Create your account</h1>
        <p className="text-sm text-zinc-500 mt-1">Start managing your microloans with Bankit</p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <label className="block text-sm font-medium text-zinc-700 mb-1">Business name</label>
          <input
            type="text"
            required
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            className="w-full px-3 py-2 border border-zinc-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900"
            placeholder="Sharma General Store"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-zinc-700 mb-1">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 py-2 border border-zinc-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900"
            placeholder="you@business.com"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-zinc-700 mb-1">
            Phone (WhatsApp) <span className="text-red-500">*</span>
          </label>
          <input
            type="tel"
            required
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="w-full px-3 py-2 border border-zinc-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900"
            placeholder="+91 98765 43210"
          />
          <p className="text-xs text-zinc-400 mt-1">Used for loan notifications via WhatsApp</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-zinc-700 mb-1">Password</label>
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 border border-zinc-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900"
            placeholder="Min. 8 characters"
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-zinc-900 text-white py-2 rounded-lg text-sm font-medium hover:bg-zinc-800 disabled:opacity-50 transition-colors"
        >
          {loading ? "Creating account..." : "Create account"}
        </button>
      </form>

      <p className="text-sm text-zinc-500 mt-6 text-center">
        Already have an account?{" "}
        <Link href="/login" className="text-zinc-900 font-medium hover:underline">
          Sign in
        </Link>
      </p>
    </>
  );
}
