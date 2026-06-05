import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-zinc-50 flex flex-col">
      {/* Nav */}
      <header className="border-b border-zinc-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <span className="text-lg font-bold tracking-tight text-zinc-900">
            Bankit
            <span className="ml-1.5 text-xs font-normal text-zinc-400">by LaunchLayer</span>
          </span>
          <div className="flex items-center gap-4">
            <Link href="/pricing" className="text-sm font-medium text-zinc-600 hover:text-zinc-900 transition-colors">
              Pricing
            </Link>
            <Link
              href="/login"
              className="text-sm font-medium bg-zinc-900 text-white px-4 py-2 rounded-lg hover:bg-zinc-800 transition-colors"
            >
              Sign in
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center text-center px-6 py-24">
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400 mb-4">
          AI-Powered Microloans
        </p>
        <h1 className="text-5xl font-bold tracking-tight text-zinc-900 max-w-2xl leading-tight">
          Instant credit for India&apos;s small merchants
        </h1>
        <p className="mt-5 text-lg text-zinc-500 max-w-xl">
          Bankit combines AI trust scoring, WhatsApp onboarding, and Polygon blockchain disbursement
          so NBFCs can lend faster and merchants can grow.
        </p>
        <div className="mt-8 flex flex-col sm:flex-row gap-3">
          <Link
            href="/signup"
            className="px-6 py-3 rounded-xl bg-zinc-900 text-white text-sm font-semibold hover:bg-zinc-800 transition-colors"
          >
            Get started free
          </Link>
          <Link
            href="/pricing"
            className="px-6 py-3 rounded-xl border border-zinc-200 bg-white text-zinc-700 text-sm font-semibold hover:bg-zinc-50 transition-colors"
          >
            View API pricing
          </Link>
        </div>

        {/* Feature strip */}
        <div className="mt-20 grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-3xl w-full text-left">
          {[
            {
              icon: "⚡",
              title: "AI Trust Scoring",
              body: "Claude-powered risk assessment gives lenders a 0–100 trust score with full explanation in seconds.",
            },
            {
              icon: "💬",
              title: "WhatsApp Onboarding",
              body: "Merchants apply, verify KYC, and track loans without leaving WhatsApp — no app install required.",
            },
            {
              icon: "🔗",
              title: "Blockchain Disbursement",
              body: "Loans are disbursed via Polygon for on-chain transparency, instant settlement, and audit trail.",
            },
          ].map((f) => (
            <div key={f.title} className="bg-white rounded-xl border border-zinc-200 p-5">
              <span className="text-2xl">{f.icon}</span>
              <h3 className="mt-3 text-sm font-semibold text-zinc-900">{f.title}</h3>
              <p className="mt-1 text-sm text-zinc-500">{f.body}</p>
            </div>
          ))}
        </div>
      </main>

      <footer className="border-t border-zinc-200 bg-white py-5 text-center text-xs text-zinc-400">
        © {new Date().getFullYear()} Awittivations LLC · Bankit ·{" "}
        <Link href="/pricing" className="hover:text-zinc-600">Pricing</Link>
      </footer>
    </div>
  );
}
