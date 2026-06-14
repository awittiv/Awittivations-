"""
Module: payload_validator.py
Description: Automated schema verification for non-custodial cross-border directives.
"""

import re
from typing import Dict, Any


class DirectiveValidationError(Exception):
    """Raised when an inbound directive violates architectural guardrails."""
    pass


class AutonomousPayloadValidator:
    def __init__(self):
        self.total_validated_directives = 0
        self._directive_pattern = re.compile(r"^dir_[a-f0-9]{32}$")
        self._hash_pattern = re.compile(r"^[a-f0-9]{64}$")

    def validate_directive(self, payload: Dict[str, Any]) -> bool:
        try:
            required_keys = [
                "directive_id",
                "compliance_model",
                "provenance_attestation",
                "credit_passport_snapshot",
                "routing_instructions",
            ]
            missing = [k for k in required_keys if k not in payload]
            if missing:
                raise DirectiveValidationError(f"Missing mandatory keys: {missing}")

            comp = payload["compliance_model"]
            if comp.get("architecture_variant") != "NON_CUSTODIAL_INTELLIGENCE_ONLY":
                raise DirectiveValidationError(
                    f"Invalid architecture variant: {comp.get('architecture_variant')}"
                )
            if comp.get("currency_possession_allowed") is not False:
                raise DirectiveValidationError(
                    "CRITICAL VULNERABILITY: Asset possession flag must be strictly False."
                )

            if not self._directive_pattern.match(payload["directive_id"]):
                raise DirectiveValidationError(
                    f"Malformed directive_id: {payload['directive_id']}"
                )

            prov = payload["provenance_attestation"]
            if not self._hash_pattern.match(prov.get("payload_hash", "")):
                raise DirectiveValidationError("Invalid cryptographic payload hash format.")
            if prov.get("signature_chain_verified") is not True:
                raise DirectiveValidationError("Data provenance chain is unsigned or compromised.")

            route = payload["routing_instructions"]
            if len(route.get("node_hop_sequence", [])) < 2:
                raise DirectiveValidationError(
                    "Insufficient node hop sequence — minimum 2 nodes required."
                )

            self.total_validated_directives += 1
            return True

        except KeyError as e:
            raise DirectiveValidationError(f"Missing internal payload attribute: {e}")


if __name__ == "__main__":
    validator = AutonomousPayloadValidator()

    sample = {
        "directive_id": "dir_e3b0c44298fc1c149afbf4c8996fb92",
        "compliance_model": {
            "architecture_variant": "NON_CUSTODIAL_INTELLIGENCE_ONLY",
            "currency_possession_allowed": False,
        },
        "provenance_attestation": {
            "payload_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "signature_chain_verified": True,
        },
        "credit_passport_snapshot": {
            "identity_hash": "id_user_0505_969",
            "risk_tier": "LOW",
            "score": 785,
        },
        "routing_instructions": {
            "origin_gateway": "US_MICH_NODE_01",
            "destination_gateway": "IN_COOP_NODE_04",
            "node_hop_sequence": ["US_MICH_NODE_01", "TPAP_INTELLIGENCE_ROUTER", "IN_COOP_NODE_04"],
        },
    }

    if validator.validate_directive(sample):
        print(f"[SUCCESS] Directive validated. Total validated: {validator.total_validated_directives}")
