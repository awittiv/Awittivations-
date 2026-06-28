# Polygon Community Grants — Season 2 Application
**Submit at:** https://polygon.questbook.xyz  
**Track:** Infrastructure + DeFi (Direct Funding Track)  
**Entity:** Awittivations LLC | UEI: L6H1T8L7ZJC6 | DUNS: 14-4151378 | EIN: 900158942

---

## Project Name
**Bankit — Non-Custodial Microloan & Grant Rails for India's 425M Unbanked Merchants**

---

## One-Line Summary
Bankit is a WhatsApp-first, AI-underwritten microloan protocol on Polygon that never holds user funds — merchants in India receive credit directly to sovereign wallets, governed by on-chain compliance and non-custodial smart contract rails aligned with RBI's National Strategy for Financial Inclusion 2025-30.

---

## Project Category
- [x] Infrastructure
- [x] DeFi
- [x] AI
- [x] Emerging Markets

---

## Project Description

### Problem
425 million small merchants in India are locked out of formal credit. Traditional banks require collateral, credit history, and physical branches. Existing fintech solutions are custodial — the platform holds funds, creating single points of failure, fraud risk, and regulatory friction. India's Reserve Bank of India launched NSFI 2025-30 (National Strategy for Financial Inclusion) with 47 mandated action points — but the infrastructure to deliver non-custodial, verifiable, last-mile credit doesn't exist.

### Solution
Bankit is a three-layer non-custodial credit protocol built entirely on Polygon:

**Layer 1 — Non-Custodial Smart Contracts**
- `BankitStablecoin.sol` — BKD token (INR-pegged, ERC-20, 6 decimals)
- `BankitLiquidityRouter.sol` — Atomic mint/burn oracle for loan disbursal
- `BankitCreditPassport.sol` — ERC-721/ERC-5192 soulbound credit identity NFT
- `RailsVault.sol` — Non-custodial vault; EIP-712 signed permits lock amount AND recipient — even a relayer cannot redirect funds
- `AtomicDisbursement.sol` — Trustless grant/loan disbursement; funds flow grantor → contract → beneficiary atomically; platform holds zero at any point
- `ComplianceAttestation.sol` — On-chain registry for RBI NSFI and SBA compliance records; gates all disbursements

**Layer 2 — AI Underwriting Pipeline**
Three parallel AI agents (FraudDetection + CreditAnalysis + PurposeViability) run simultaneously using Claude Haiku, synthesizing a trust score in under 3 seconds. No FICO score required. No bank account required. A WhatsApp message is the entire application.

**Layer 3 — Non-Custodial Grant Rails (new)**
A separate FastAPI service tracks SBA and NSFI-aligned grant applications for all Awittivations projects. Compliance hashes are written on-chain via `ComplianceAttestation`; beneficiaries claim directly from `AtomicDisbursement` without platform involvement.

### How It Works (User Flow)
1. Merchant sends WhatsApp message: "I need ₹5,000 for inventory"
2. Bankit extracts intent, runs KYC gate, triggers 3-agent AI trust score
3. TPAP corridor check verifies cross-border compliance
4. Loan approved → BKD minted on Polygon → sent directly to merchant's sovereign HD wallet
5. Atomic Sweep deducts real-time tax withholding (India + US compliance)
6. Credit Passport NFT minted/updated on-chain — permanent, soulbound credit history
7. Repayment via signed EIP-712 mandate — non-custodial, no bank middleman

**Platform possession of funds at any point: ZERO.**

---

## Why Polygon

Polygon is the only L2 that makes this economically viable for India's unbanked:

- **Gas fees**: Sub-cent transactions make ₹500 ($6) microloans profitable — impossible on L1
- **Speed**: 2-second finality matches WhatsApp UX expectations
- **EVM compatibility**: Full Solidity + Foundry toolchain; 70 passing tests today
- **Ecosystem**: Polygon co-founder Sandeep Nailwal's explicit commitment to emerging markets aligns exactly with our mission
- **Already live on mainnet**: All 6 contracts are deployed and verifiable on Polygon mainnet (chain 137) today, backed by 70/70 Foundry tests. The protocol is built, tested, and on-chain — this grant hardens and scales it, it does not bootstrap it.

Bankit is Polygon-native by design — built, tested, and **deployed** end-to-end on Polygon. This grant is not a migration and not a first deployment; it funds the security hardening, onboarding, and scale that turn a live protocol into a production lending rail.

---

## Traction & Technical Proof

| Metric | Status |
|---|---|
| Smart contracts written | 6 (3 core + 3 rails) |
| Foundry tests | **70/70 passing** |
| Mainnet deployment | **All 6 contracts live on Polygon mainnet (chain 137)** |
| Backend services | FastAPI + Supabase + Twilio WhatsApp |
| AI agents | 3 parallel (Claude Haiku) |
| Wallets | Sovereign HD wallet auto-assigned per merchant at signup |
| Credit Passport | ERC-721/ERC-5192 soulbound NFT — on-chain credit history |
| Non-custodial rails | RailsVault + AtomicDisbursement + ComplianceAttestation — live on mainnet |
| RBI alignment | Full NSFI 2025-30 Panch-Jyoti (all 5 pillars) compliance report generated |
| Entity registration | UEI L6H1T8L7ZJC6 / DUNS 14-4151378 / EIN 900158942 — SBA-ready |
| GitHub | All code committed, open |

---

## Team

**Awittivations LLC** — Michigan, USA  
Founder & Lead Developer: Albert Wittiv (awittiv)  

- Full-stack AI + blockchain development
- RBI regulatory research and NSFI 2025-30 alignment
- SBA grant tracking infrastructure
- WhatsApp conversational banking pipeline
- Multi-agent AI underwriting system

---

## Milestones & Budget

**Total Requested: 150,000 POL**

### Milestone 1 — Security Hardening & Multisig Governance (30,000 POL)
The 6 contracts are already live on Polygon mainnet. Before scaling real merchant funds through them, governance must move off the single hot key that deployed them. This milestone removes that single point of failure:
- Deploy a **Gnosis Safe (2-of-3)** on Polygon and migrate `DEFAULT_ADMIN_ROLE`, `COMPLIANCE_ROLE` (pause), and `AtomicDisbursement` ownership from the hot key to the Safe (migration script + runbook already written)
- Renounce the hot key's governance roles after a proven Safe-controlled action; leave only operational `ORACLE_ROLE`/`ATTESTER_ROLE` on a minimal-funded ops key
- Move the wallet master seed out of plaintext `.env` into a managed secret store; cap ops-key POL exposure
- Commission an external **smart-contract security audit** of all 6 contracts and remediate findings
- Verify all contracts on Polygonscan and publish addresses
- **Deliverable:** 2-of-3 Safe controlling all admin roles, hot-key governance renounced, audit report published, 6 verified contracts on Polygonscan

### Milestone 2 — WhatsApp Merchant Onboarding (40,000 POL)
- Production Twilio WhatsApp sandbox → business number
- Aadhaar eKYC integration surface (UIDAI AUA interface)
- Merchant sovereign wallet auto-assignment at signup
- Live end-to-end loan: WhatsApp → AI score → BKD mint → wallet
- **Deliverable:** 50 merchants onboarded, 10 live loans disbursed

### Milestone 3 — Credit Passport & Repayment Rail (30,000 POL)
- Credit Passport NFT minting for all onboarded merchants
- EIP-712 repayment mandates (non-custodial NACH equivalent)
- Atomic Sweep tax withholding live
- Credit score updates on-chain post-repayment
- **Deliverable:** 10 loans fully repaid, passports updated on-chain

### Milestone 4 — Non-Custodial Grant Rails Live (30,000 POL)
- `AtomicDisbursement` live for SBA + NSFI grant disbursements
- `ComplianceAttestation` writing real compliance hashes
- `/grants/entity` API returning Awittivations UEI/DUNS/EIN for downstream SBA systems
- NSFI Panch-Jyoti compliance report endpoint live
- **Deliverable:** 1 real grant committed and claimed through rails

### Milestone 5 — Scale & Open Source (20,000 POL)
- Open source the non-custodial rails contracts under MIT license
- Developer documentation for `RailsVault` + `AtomicDisbursement` integration
- Submit to Polygon ecosystem directory
- Pitch to 3 additional India fintech teams for rails adoption
- **Deliverable:** Public repo, docs, 3 partner conversations

---

## Impact Metrics (12 months)

| Metric | Target |
|---|---|
| Merchants onboarded | 500 |
| Loans disbursed | 200 |
| Total loan volume | ₹10,00,000 (~$12,000) |
| Credit Passports minted | 500 |
| Grant disbursements via Rails | 5 |
| NSFI pillars addressed | All 5 (Panch-Jyoti) |
| Other teams using Rails | 3+ |
| Platform custody of funds | 0 at all times |

---

## Regulatory Alignment

- **RBI NSFI 2025-30**: All 5 Panch-Jyoti pillars addressed. Non-custodial design directly implements pillar 5 (customer protection) — platform holds zero funds.
- **RBI Digital Payments**: Aligns with RBI Payments Vision 2028 — "user empowerment" and "fraud prevention" via on-chain audit trail.
- **SBA Compliance**: UEI, DUNS, EIN registered. SBA 7(a) and EIDL applications tracked via ComplianceAttestation rails.
- **Michigan NBFC**: Michigan 2026-03-BT compliant loan pipeline.
- **FATF Non-Custodial**: Bankit is a non-custodial protocol — merchants control their own wallets. Platform is the rails, not the bank.

---

## Links

- GitHub: https://github.com/awittiv/Awittivations-
- Contract Tests: `cd bankit/contracts && forge test` → 70/70 passing
- Application portal: https://polygon.questbook.xyz

**Live Polygon mainnet contracts (chain 137):**
- `BankitStablecoin` — `0x920DBEFF9900cE3B37f76754C05fa15c6575822E`
- `BankitLiquidityRouter` — `0x5fc2180fAA7ac70c6a6F22796253Be89F45022Cf`
- `BankitCreditPassport` — `0x8010dFF392691371999F1B6C88001EB998a01129`
- `ComplianceAttestation` — `0x8BdA80df379555EEd9A1a45dc959C41f9e01335c`
- `AtomicDisbursement` — `0xc3d3150A7d0a5fD1aC85f048fe283d2F82083396`
- `RailsVault` — `0xb66aebf16Dc6A77B0cfC49d10A4295d388ecf4Ff`

---

## Additional Context

Polygon already funded a WhatsApp + stablecoin + emerging markets grantee in Season 2. Bankit is the India-native, RBI-compliant, fully non-custodial version of that thesis — with AI underwriting, sovereign wallets, soulbound credit passports, and non-custodial grant rails built on top. We are not building toward Polygon — we are already live on Polygon, with all six contracts deployed to mainnet today. This grant hardens that live protocol (multisig governance + audit), onboards real merchants, and puts credit in the hands of India's 425 million unbanked.
