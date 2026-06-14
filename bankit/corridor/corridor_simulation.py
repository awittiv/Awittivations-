"""
Module: corridor_simulation.py
Description: End-to-end telemetry pipeline runner simulating structural data
             bursts between the US and Indian co-op banking gateway vectors.
"""

import os  # Fixed: was incorrectly placed at bottom of file
import time
import random
from credit_passport_engine import AutonomousOrchestrationEngine, TransactionContext
from payload_validator import AutonomousPayloadValidator, DirectiveValidationError

ANOMALY_TYPES = ["CUSTODIAL_BREACH", "UNSIGNED_DATA", "MALFORMED_ROUTE"]


class CrossBorderSimulationHarness:
    def __init__(self):
        self.orchestrator = AutonomousOrchestrationEngine()
        self.validator = AutonomousPayloadValidator()
        self.identities = [
            "acc_0505_mich_alpha",
            "acc_1969_in_gateway",
            "acc_coop_mumbai_09",
            "acc_coop_muskegon_12",
        ]
        self.corridor_nodes = ["US_MICH_NODE_01", "TPAP_INTELLIGENCE_ROUTER", "IN_COOP_NODE_04"]

    def generate_mock_telemetry_burst(self, inject_anomaly: bool = False, anomaly_type: str | None = None) -> dict:
        source = random.choice(self.identities[:2])
        payload_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        signature_state = True
        currency_flag = False
        architecture_string = "NON_CUSTODIAL_INTELLIGENCE_ONLY"

        if inject_anomaly:
            chosen = anomaly_type or random.choice(ANOMALY_TYPES)
            if chosen == "CUSTODIAL_BREACH":
                currency_flag = True
            elif chosen == "UNSIGNED_DATA":
                signature_state = False
            elif chosen == "MALFORMED_ROUTE":
                architecture_string = "ILLEGAL_CUSTODIAL_CORE"

        return {
            "directive_id": f"dir_{os.urandom(16).hex()}",
            "compliance_model": {
                "architecture_variant": architecture_string,
                "currency_possession_allowed": currency_flag,
            },
            "provenance_attestation": {
                "payload_hash": payload_hash,
                "signature_chain_verified": signature_state,
            },
            "credit_passport_snapshot": {
                "identity_hash": source,
                "risk_tier": random.choice(["LOW", "MEDIUM"]),
                "score": random.randint(680, 830),
            },
            "routing_instructions": {
                "origin_gateway": self.corridor_nodes[0],
                "destination_gateway": self.corridor_nodes[2],
                "node_hop_sequence": self.corridor_nodes,
            },
        }

    def execute_loop(self, iterations: int = 5):
        print(f"\n[STARTING SIMULATION] Executing {iterations} telemetry pipeline passes...")
        print("-" * 70)

        results = {"passed": 0, "blocked": 0, "errors": 0}

        for index in range(1, iterations + 1):
            # Cycle through all anomaly types deterministically for reproducible test results
            if index == 3:
                should_anomaly = True
                anomaly_type = ANOMALY_TYPES[(index - 1) % len(ANOMALY_TYPES)]
            else:
                should_anomaly = False
                anomaly_type = None

            raw_payload = self.generate_mock_telemetry_burst(
                inject_anomaly=should_anomaly, anomaly_type=anomaly_type
            )

            print(f"\nPass [{index}/{iterations}] - Target Directive: {raw_payload['directive_id']}")
            if should_anomaly:
                print(f">> [INJECTING ANOMALY: {anomaly_type}]")

            try:
                self.validator.validate_directive(raw_payload)
                print("  Step 1: Schema Boundary Validation -> [PASSED]")

                snapshot = raw_payload["credit_passport_snapshot"]
                context = TransactionContext(
                    source_identity=snapshot["identity_hash"],
                    destination_identity=raw_payload["routing_instructions"]["destination_gateway"],
                    requested_liquidity_path=raw_payload["routing_instructions"]["node_hop_sequence"],
                    historical_vectors={
                        "repayment_velocity": 1.20 if snapshot["score"] > 750 else 0.95,
                        "liquidity_utilization": 0.18,
                    },
                    telemetry_data={
                        "source_payload_hash": raw_payload["provenance_attestation"]["payload_hash"],
                        "is_cryptographically_signed": raw_payload["provenance_attestation"]["signature_chain_verified"],
                    },
                )

                result = self.orchestrator.execute_intelligence_pass(context)
                print(f"  Step 2: Multi-Agent Intelligence Synthesis -> [SUCCESS] Status: {result['status']}")
                results["passed"] += 1

            except DirectiveValidationError as e:
                print(f"  Step 1: Schema Boundary Validation -> [BLOCKED]: {e}")
                results["blocked"] += 1
            except Exception as e:
                print(f"  Pipeline Interrupted: {e}")
                results["errors"] += 1

            time.sleep(0.3)

        print(f"\n{'='*70}")
        print(f"Simulation Complete — Passed: {results['passed']} | Blocked: {results['blocked']} | Errors: {results['errors']}")
        print(f"{'='*70}\n")


if __name__ == "__main__":
    harness = CrossBorderSimulationHarness()
    harness.execute_loop(iterations=4)
