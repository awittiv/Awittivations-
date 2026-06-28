// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/BankitStablecoin.sol";
import "../src/BankitLiquidityRouter.sol";
import "../src/BankitCreditPassport.sol";
import "../src/ComplianceAttestation.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title TransferToMultisig
/// @notice Migrates Bankit GOVERNANCE/admin control from the single hot oracle
///         key to a Gnosis Safe multisig. Operational roles (ORACLE_ROLE on the
///         router + passport, ATTESTER_ROLE on compliance) are intentionally LEFT
///         on the current hot key so the backend keeps disbursing without manual
///         multisig signing.
///
///         Governance moved to the Safe:
///           BankitStablecoin       DEFAULT_ADMIN_ROLE + COMPLIANCE_ROLE (pause)
///           BankitLiquidityRouter  DEFAULT_ADMIN_ROLE
///           BankitCreditPassport   DEFAULT_ADMIN_ROLE
///           ComplianceAttestation  DEFAULT_ADMIN_ROLE
///           AtomicDisbursement     Ownable owner
///
/// TWO PHASES (run separately — never renounce before the Safe is proven):
///
///   PHASE 1 — GRANT (default, fully reversible: old key keeps admin as backup)
///     MULTISIG=0xSafe... \
///     forge script script/TransferToMultisig.s.sol:TransferToMultisig \
///       --rpc-url polygon --broadcast -vvvv
///
///   --- between phases: do a test action FROM the Safe (e.g. pause then unpause
///       the stablecoin) to prove the Safe controls the contracts. ---
///
///   PHASE 2 — FINALIZE (irreversible: transfers Ownable + renounces old admin)
///     MULTISIG=0xSafe... FINALIZE=true \
///     forge script script/TransferToMultisig.s.sol:TransferToMultisig \
///       --rpc-url polygon --broadcast -vvvv
///
/// Required env:
///   ORACLE_PRIVATE_KEY            — current admin/deployer key (the broadcaster)
///   MULTISIG                      — the Gnosis Safe address to receive governance
///   STABLECOIN_ADDRESS, CONTRACT_ADDRESS (router), PASSPORT_ADDRESS,
///   COMPLIANCE_ATTESTATION_ADDRESS, ATOMIC_DISBURSEMENT_ADDRESS
/// Optional env:
///   FINALIZE=true                 — run phase 2 (default false = phase 1)
contract TransferToMultisig is Script {
    function run() external {
        uint256 adminKey = vm.envUint("ORACLE_PRIVATE_KEY");
        address admin    = vm.addr(adminKey);
        address safe     = vm.envAddress("MULTISIG");
        bool finalize    = vm.envOr("FINALIZE", false);

        BankitStablecoin      coin   = BankitStablecoin(vm.envAddress("STABLECOIN_ADDRESS"));
        BankitLiquidityRouter router = BankitLiquidityRouter(vm.envAddress("CONTRACT_ADDRESS"));
        BankitCreditPassport  pass   = BankitCreditPassport(vm.envAddress("PASSPORT_ADDRESS"));
        ComplianceAttestation comp   = ComplianceAttestation(vm.envAddress("COMPLIANCE_ATTESTATION_ADDRESS"));
        address atomic               = vm.envAddress("ATOMIC_DISBURSEMENT_ADDRESS");

        require(safe != address(0), "MULTISIG is zero address");
        require(safe != admin, "MULTISIG equals admin key");
        require(safe.code.length > 0, "MULTISIG has no code (not a deployed Safe?)");

        bytes32 ADMIN_ROLE      = 0x00; // DEFAULT_ADMIN_ROLE
        bytes32 COMPLIANCE_ROLE = coin.COMPLIANCE_ROLE();

        if (!finalize) {
            // ── PHASE 1: GRANT governance to the Safe (old key retained) ──
            console2.log("=== PHASE 1: GRANT to Safe ===", safe);
            vm.startBroadcast(adminKey);

            coin.grantRole(ADMIN_ROLE, safe);
            coin.grantRole(COMPLIANCE_ROLE, safe);
            router.grantRole(ADMIN_ROLE, safe);
            pass.grantRole(ADMIN_ROLE, safe);
            comp.grantRole(ADMIN_ROLE, safe);

            vm.stopBroadcast();

            _assertSafeHasGovernance(coin, router, pass, comp, COMPLIANCE_ROLE, safe);
            console2.log("Phase 1 complete. Safe now co-admin; old key still admin (backup).");
            console2.log("NEXT: from the Safe, call coin.pause() then coin.unpause() to prove control.");
            console2.log("THEN: re-run with FINALIZE=true to transfer ownership and drop the old key.");
        } else {
            // ── PHASE 2: FINALIZE — transfer Ownable + renounce old admin ──
            console2.log("=== PHASE 2: FINALIZE ===");

            // Guard: refuse to renounce unless the Safe already holds everything.
            require(coin.hasRole(ADMIN_ROLE, safe),      "Safe missing coin admin");
            require(coin.hasRole(COMPLIANCE_ROLE, safe), "Safe missing coin compliance");
            require(router.hasRole(ADMIN_ROLE, safe),    "Safe missing router admin");
            require(pass.hasRole(ADMIN_ROLE, safe),      "Safe missing passport admin");
            require(comp.hasRole(ADMIN_ROLE, safe),      "Safe missing compliance admin");

            vm.startBroadcast(adminKey);

            // Ownable single-step transfer (AtomicDisbursement).
            Ownable(atomic).transferOwnership(safe);

            // Drop the old key's GOVERNANCE roles. ORACLE_ROLE / ATTESTER_ROLE on
            // the old key are deliberately NOT touched — backend keeps signing.
            coin.renounceRole(COMPLIANCE_ROLE, admin);
            coin.renounceRole(ADMIN_ROLE, admin);
            router.renounceRole(ADMIN_ROLE, admin);
            pass.renounceRole(ADMIN_ROLE, admin);
            comp.renounceRole(ADMIN_ROLE, admin);

            vm.stopBroadcast();

            require(Ownable(atomic).owner() == safe, "AtomicDisbursement owner != Safe");
            require(!coin.hasRole(ADMIN_ROLE, admin),      "old key still coin admin");
            require(!coin.hasRole(COMPLIANCE_ROLE, admin), "old key still coin compliance");
            require(!router.hasRole(ADMIN_ROLE, admin),    "old key still router admin");
            require(!pass.hasRole(ADMIN_ROLE, admin),      "old key still passport admin");
            require(!comp.hasRole(ADMIN_ROLE, admin),      "old key still compliance admin");

            console2.log("Phase 2 complete. Governance fully on the Safe; old key is ops-only.");
        }
    }

    function _assertSafeHasGovernance(
        BankitStablecoin coin,
        BankitLiquidityRouter router,
        BankitCreditPassport pass,
        ComplianceAttestation comp,
        bytes32 COMPLIANCE_ROLE,
        address safe
    ) internal view {
        bytes32 ADMIN_ROLE = 0x00;
        require(coin.hasRole(ADMIN_ROLE, safe),      "grant failed: coin admin");
        require(coin.hasRole(COMPLIANCE_ROLE, safe), "grant failed: coin compliance");
        require(router.hasRole(ADMIN_ROLE, safe),    "grant failed: router admin");
        require(pass.hasRole(ADMIN_ROLE, safe),      "grant failed: passport admin");
        require(comp.hasRole(ADMIN_ROLE, safe),      "grant failed: compliance admin");
    }
}
