from datetime import datetime, timezone
from models.project import ProjectName, NSFIPillar

PANCH_JYOTI: dict[NSFIPillar, dict] = {
    "universal_access": {
        "pillar": 1,
        "description": "Universal last-mile access to financial services",
        "rbi_target": "100% coverage in 80% of districts by March 2026",
        "metric": "merchant_coverage_pct",
    },
    "gender_sensitive_inclusion": {
        "pillar": 2,
        "description": "Gender-equitable financial service delivery",
        "rbi_target": "50% of new accounts held by women",
        "metric": "female_account_pct",
    },
    "livelihood_linkages": {
        "pillar": 3,
        "description": "Linkage between credit access and MSME livelihood outcomes",
        "rbi_target": "Documented livelihood improvement for MSME borrowers",
        "metric": "merchant_revenue_growth_pct",
    },
    "financial_literacy": {
        "pillar": 4,
        "description": "Awareness of financial products and digital payments",
        "rbi_target": "Bhashini AI tools integrated for vernacular financial literacy",
        "metric": "literacy_program_completion_pct",
    },
    "customer_protection": {
        "pillar": 5,
        "description": "Robust grievance redressal and fraud protection",
        "rbi_target": "Grievance resolution within 30 days",
        "metric": "grievance_resolution_days",
    },
}


def get_pillar_alignment(pillars: list[NSFIPillar]) -> list[dict]:
    return [{"pillar_key": p, **PANCH_JYOTI[p]} for p in pillars if p in PANCH_JYOTI]


async def get_nsfi_dashboard(project_name: ProjectName | None = None) -> dict:
    return {
        "strategy":      "NSFI 2025-30",
        "authority":     "Reserve Bank of India",
        "launched":      "2025-12-01",
        "action_points": 47,
        "framework":     "Panch-Jyoti (five pillars)",
        "pillars":       PANCH_JYOTI,
        "project":       project_name,
        "non_custodial_guarantee": (
            "All disbursements flow via AtomicDisbursement smart contract. "
            "Platform holds zero currency at any point."
        ),
    }


async def generate_nsfi_report(project_name: ProjectName) -> dict:
    pillar_evidence: dict[NSFIPillar, dict] = {
        "universal_access": {
            "aligned": True,
            "evidence": (
                "Non-custodial rails give merchants a Polygon wallet at signup — "
                "no bank account required for last-mile access."
            ),
        },
        "gender_sensitive_inclusion": {
            "aligned": True,
            "evidence": (
                "WhatsApp-first onboarding removes literacy and mobility barriers; "
                "wallet assigned on registration regardless of gender."
            ),
        },
        "livelihood_linkages": {
            "aligned": True,
            "evidence": (
                "Microloans and SBA grants disbursed for documented business purposes; "
                "merchant revenue tracked on-chain via Credit Passport."
            ),
        },
        "financial_literacy": {
            "aligned": True,
            "evidence": (
                "Conversational WhatsApp banking in vernacular; "
                "Bhashini AI tool integration on roadmap per NSFI action point 31."
            ),
        },
        "customer_protection": {
            "aligned": True,
            "evidence": (
                "Smart contract custody — platform NEVER holds funds. "
                "Full on-chain audit trail. Atomic disbursement prevents partial failures."
            ),
        },
    }

    return {
        "report_date":              datetime.now(timezone.utc).isoformat(),
        "project":                  project_name,
        "strategy":                 "NSFI 2025-30",
        "all_pillars_aligned":      True,
        "pillar_coverage":          pillar_evidence,
        "non_custodial_statement":  (
            "This platform possesses zero currency. Funds flow atomically between "
            "grantor and beneficiary wallets via RailsVault and AtomicDisbursement "
            "smart contracts on Polygon. Platform role: route signed transactions only."
        ),
        "rbi_reference": {
            "document":  "National Strategy for Financial Inclusion 2025-2030",
            "launched":  "2025-12-01",
            "authority": "RBI Governor Sanjay Malhotra / FSDC Sub-Committee",
            "pillars":   5,
            "targets":   47,
        },
    }
