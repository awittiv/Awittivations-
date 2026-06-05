import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pricing — Bankit Trust Scoring API",
  description: "Simple, transparent pricing for the Bankit Trust Scoring API. Start free, scale as you grow.",
};

const tiers = [
  {
    name: "Starter",
    price: "$49",
    period: "/month",
    description: "For NBFCs testing AI-powered credit scoring.",
    requests: "100 API calls / month",
    highlight: false,
    cta: "Get started",
    ctaHref: "mailto:api@bankit.in?subject=Starter%20API%20Key%20Request",
    features: [
      "100 Trust Score requests / month",
      "Composite score (0–100) + risk label",
      "JSON response with key risk signals",
      "Email support (48h SLA)",
      "API key via email",
    ],
  },
  {
    name: "Growth",
    price: "$199",
    period: "/month",
    description: "For active lenders processing real loan volume.",
    requests: "1,000 API calls / month",
    highlight: true,
    cta: "Get started",
    ctaHref: "mailto:api@bankit.in?subject=Growth%20API%20Key%20Request",
    features: [
      "1,000 Trust Score requests / month",
      "Full score breakdown + narrative explanation",
      "Webhook events (score.completed, key.quota_warning)",
      "Priority email support (24h SLA)",
      "Dashboard access (usage & key management)",
      "Monthly usage report",
    ],
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "For banks and large NBFCs with high-volume needs.",
    requests: "Unlimited API calls",
    highlight: false,
    cta: "Contact sales",
    ctaHref: "mailto:api@bankit.in?subject=Enterprise%20Inquiry",
    features: [
      "Unlimited Trust Score requests",
      "Custom model tuning on your loan portfolio",
      "Dedicated support + implementation help",
      "99.9% uptime SLA",
      "On-premise / private cloud deployment option",
      "SSO + team access controls",
    ],
  },
];

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-zinc-50">
      {/* Nav */}
      <header className="border-b border-zinc-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/" className="text-lg font-bold tracking-tight text-zinc-900">
            Bankit
            <span className="ml-1.5 text-xs font-normal text-zinc-400">Trust Scoring API</span>
          </Link>
          <Link
            href="/login"
            className="text-sm font-medium text-zinc-600 hover:text-zinc-900 transition-colors"
          >
            Sign in →
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-5xl mx-auto px-6 pt-16 pb-12 text-center">
        <h1 className="text-4xl font-semibold tracking-tight text-zinc-900">
          Simple, transparent pricing
        </h1>
        <p className="mt-3 text-lg text-zinc-500 max-w-xl mx-auto">
          Pay only for what you use. No setup fees, no hidden charges.
          Scale your NBFC with AI credit scoring from day one.
        </p>
      </section>

      {/* Pricing cards */}
      <section className="max-w-5xl mx-auto px-6 pb-20">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {tiers.map((tier) => (
            <div
              key={tier.name}
              className={`rounded-2xl border p-7 flex flex-col ${
                tier.highlight
                  ? "bg-zinc-900 border-zinc-900 text-white"
                  : "bg-white border-zinc-200 text-zinc-900"
              }`}
            >
              {tier.highlight && (
                <span className="self-start mb-3 text-xs font-semibold uppercase tracking-widest text-zinc-400">
                  Most popular
                </span>
              )}

              <h2 className={`text-xl font-semibold ${tier.highlight ? "text-white" : "text-zinc-900"}`}>
                {tier.name}
              </h2>
              <p className={`mt-1 text-sm ${tier.highlight ? "text-zinc-400" : "text-zinc-500"}`}>
                {tier.description}
              </p>

              <div className="mt-6 flex items-baseline gap-1">
                <span className={`text-4xl font-bold tracking-tight ${tier.highlight ? "text-white" : "text-zinc-900"}`}>
                  {tier.price}
                </span>
                {tier.period && (
                  <span className={`text-sm ${tier.highlight ? "text-zinc-400" : "text-zinc-500"}`}>
                    {tier.period}
                  </span>
                )}
              </div>

              <p className={`mt-2 text-xs font-medium ${tier.highlight ? "text-zinc-300" : "text-zinc-500"}`}>
                {tier.requests}
              </p>

              <a
                href={tier.ctaHref}
                className={`mt-6 block w-full text-center py-2.5 rounded-xl text-sm font-semibold transition-colors ${
                  tier.highlight
                    ? "bg-white text-zinc-900 hover:bg-zinc-100"
                    : "bg-zinc-900 text-white hover:bg-zinc-800"
                }`}
              >
                {tier.cta}
              </a>

              <ul className="mt-7 flex flex-col gap-3">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-start gap-2.5 text-sm">
                    <span className={`mt-0.5 shrink-0 ${tier.highlight ? "text-zinc-400" : "text-zinc-400"}`}>
                      ✓
                    </span>
                    <span className={tier.highlight ? "text-zinc-300" : "text-zinc-700"}>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* FAQ strip */}
        <div className="mt-14 grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            {
              q: "What counts as one API call?",
              a: "Each POST to /v1/score counts as one request, regardless of score outcome.",
            },
            {
              q: "What happens when I hit my limit?",
              a: "Requests return HTTP 429. Usage resets on the 1st of each month. Upgrade anytime.",
            },
            {
              q: "Can I change tiers mid-month?",
              a: "Yes. Upgrades take effect immediately. Contact api@bankit.in to change your plan.",
            },
          ].map((item) => (
            <div key={item.q} className="bg-white rounded-xl border border-zinc-200 p-5">
              <p className="text-sm font-semibold text-zinc-900">{item.q}</p>
              <p className="mt-1.5 text-sm text-zinc-500">{item.a}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
