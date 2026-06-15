// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/ComplianceAttestation.sol";

contract ComplianceAttestationTest is Test {
    ComplianceAttestation compliance;

    address admin        = makeAddr("admin");
    address attester     = makeAddr("attester");
    address unauthorized = makeAddr("unauthorized");

    bytes32 projectBankit = keccak256("bankit");
    bytes32 projectBRF    = keccak256("brf");
    bytes32 hash1         = keccak256("sba-7a-2026-001");
    bytes32 hash2         = keccak256("sba-7a-2026-002");
    bytes32 hashNSFI      = keccak256("nsfi-livelihood-001");

    function setUp() public {
        vm.prank(admin);
        compliance = new ComplianceAttestation(admin);
    }

    function test_attest_sba7a() public {
        vm.prank(admin);
        compliance.attest(hash1, projectBankit, 0, 3, "SBA-7A-2026-001", 250_000_00);

        assertTrue(compliance.isAttested(hash1));
        ComplianceAttestation.Attestation memory a = compliance.getAttestation(hash1);
        assertEq(a.projectId,      projectBankit);
        assertEq(a.programType,    0);
        assertEq(a.nsfiPillar,     3);
        assertEq(a.applicationRef, "SBA-7A-2026-001");
        assertEq(a.amountUSDCents, 250_000_00);
        assertEq(a.attester,       admin);
        assertTrue(a.active);
    }

    function test_attest_nsfi() public {
        vm.prank(admin);
        compliance.attest(hashNSFI, projectBankit, 5, 3, "NSFI-LIVELIHOOD-001", 0);

        assertTrue(compliance.isAttested(hashNSFI));
        ComplianceAttestation.Attestation memory a = compliance.getAttestation(hashNSFI);
        assertEq(a.programType, 5); // NSFI
        assertEq(a.nsfiPillar,  3); // LIVELIHOOD_LINKAGES
    }

    function test_revoke() public {
        vm.startPrank(admin);
        compliance.attest(hash1, projectBankit, 0, 3, "SBA-7A-2026-001", 250_000_00);
        assertTrue(compliance.isAttested(hash1));
        compliance.revoke(hash1);
        vm.stopPrank();

        assertFalse(compliance.isAttested(hash1));
    }

    function test_addAttesterRole() public {
        bytes32 attesterRole = compliance.ATTESTER_ROLE();
        vm.startPrank(admin);
        compliance.grantRole(attesterRole, attester);
        vm.stopPrank();

        vm.prank(attester);
        compliance.attest(hash1, projectBRF, 1, 0, "SBA-SBLC-001", 100_000_00);

        assertTrue(compliance.isAttested(hash1));
    }

    function test_revert_unauthorizedAttest() public {
        vm.prank(unauthorized);
        vm.expectRevert();
        compliance.attest(hash1, projectBankit, 0, 0, "REF", 0);
    }

    function test_revert_revokeInactive() public {
        vm.prank(admin);
        vm.expectRevert("ComplianceAttestation: not active");
        compliance.revoke(hash1);
    }

    function test_revert_doubleAttest() public {
        vm.startPrank(admin);
        compliance.attest(hash1, projectBankit, 0, 3, "REF", 0);
        vm.expectRevert("ComplianceAttestation: already attested");
        compliance.attest(hash1, projectBankit, 0, 3, "REF", 0);
        vm.stopPrank();
    }

    function test_projectAttestations_multipleGrants() public {
        vm.startPrank(admin);
        compliance.attest(hash1,    projectBankit, 0, 3, "SBA-001", 250_000_00);
        compliance.attest(hash2,    projectBankit, 3, 1, "EIDL-001", 100_000_00);
        compliance.attest(hashNSFI, projectBRF,    5, 3, "NSFI-001", 0);
        vm.stopPrank();

        bytes32[] memory bankitHashes = compliance.getProjectAttestations(projectBankit);
        assertEq(bankitHashes.length, 2);

        bytes32[] memory brfHashes = compliance.getProjectAttestations(projectBRF);
        assertEq(brfHashes.length, 1);
    }

    function test_attestation_timestamp() public {
        vm.warp(1_700_000_000);
        vm.prank(admin);
        compliance.attest(hash1, projectBankit, 0, 3, "REF", 0);

        ComplianceAttestation.Attestation memory a = compliance.getAttestation(hash1);
        assertEq(a.attestedAt, 1_700_000_000);
    }
}
