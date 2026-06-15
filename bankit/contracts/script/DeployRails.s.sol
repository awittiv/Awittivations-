// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/RailsVault.sol";
import "../src/ComplianceAttestation.sol";
import "../src/AtomicDisbursement.sol";

/// @notice Deploy the three non-custodial rails contracts.
/// Order: ComplianceAttestation → AtomicDisbursement (needs compliance addr) → RailsVault
///
/// Usage:
///   forge script script/DeployRails.s.sol --rpc-url amoy --broadcast --verify
///
/// Set env vars before running:
///   DEPLOYER_ADDRESS  — deployer / admin wallet
///   DEPLOYER_KEY      — deployer private key (or use --ledger)
contract DeployRails is Script {
    function run() external {
        address deployer = vm.envAddress("DEPLOYER_ADDRESS");
        uint256 key      = vm.envUint("DEPLOYER_KEY");

        vm.startBroadcast(key);

        ComplianceAttestation compliance = new ComplianceAttestation(deployer);
        AtomicDisbursement    disburse   = new AtomicDisbursement(address(compliance));
        RailsVault            vault      = new RailsVault();

        vm.stopBroadcast();

        console.log("ComplianceAttestation:", address(compliance));
        console.log("AtomicDisbursement:   ", address(disburse));
        console.log("RailsVault:           ", address(vault));
        console.log("");
        console.log("Set in .env:");
        console.log("COMPLIANCE_ATTESTATION_ADDRESS=", address(compliance));
        console.log("ATOMIC_DISBURSEMENT_ADDRESS=",    address(disburse));
        console.log("RAILS_VAULT_ADDRESS=",             address(vault));
    }
}
