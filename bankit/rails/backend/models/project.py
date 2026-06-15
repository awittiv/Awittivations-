from typing import Literal

ProjectName = Literal[
    "bankit",
    "brf",
    "launchlayer",
    "awittivations_main",
]

SBAProgramType = Literal[
    "sba_7a",
    "sba_sblc",
    "sba_made_in_america",
    "sba_eidl",
    "sba_microloan",
    "nsfi",
]

NSFIPillar = Literal[
    "universal_access",
    "gender_sensitive_inclusion",
    "livelihood_linkages",
    "financial_literacy",
    "customer_protection",
]

# Maps to uint8 programType in ComplianceAttestation.sol
PROGRAM_TYPE_ID: dict[str, int] = {
    "sba_7a":              0,
    "sba_sblc":            1,
    "sba_made_in_america": 2,
    "sba_eidl":            3,
    "sba_microloan":       4,
    "nsfi":                5,
}

# Maps to uint8 nsfiPillar in ComplianceAttestation.sol
NSFI_PILLAR_ID: dict[str, int] = {
    "universal_access":           1,
    "gender_sensitive_inclusion": 2,
    "livelihood_linkages":        3,
    "financial_literacy":         4,
    "customer_protection":        5,
}

ALL_PROJECTS: list[ProjectName] = [
    "bankit",
    "brf",
    "launchlayer",
    "awittivations_main",
]
