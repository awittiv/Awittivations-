// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/AtomicDisbursement.sol";
import "../src/ComplianceAttestation.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockToken is ERC20 {
    constructor() ERC20("MockToken", "MCK") {
        _mint(msg.sender, 10_000_000e18);
    }
}

contract AtomicDisbursementTest is Test {
    ComplianceAttestation compliance;
    AtomicDisbursement    disburse;
    MockToken             token;

    address admin       = makeAddr("admin");
    address grantor     = makeAddr("grantor");
    address beneficiary = makeAddr("beneficiary");
    address attacker    = makeAddr("attacker");

    bytes32 projectBankit = keccak256("bankit");
    bytes32 projectBRF    = keccak256("brf");
    bytes32 compHash      = keccak256("sba-7a-2026-001");

    function setUp() public {
        vm.startPrank(admin);
        compliance = new ComplianceAttestation(admin);
        disburse   = new AtomicDisbursement(address(compliance));
        token      = new MockToken();
        token.transfer(grantor, 1_000_000e18);
        vm.stopPrank();
    }

    function _attest(bytes32 hash, bytes32 projectId) internal {
        vm.prank(admin);
        compliance.attest(hash, projectId, 0, 3, "SBA-7A-2026-001", 250_000_00);
    }

    function _commit(
        bytes32 hash,
        bytes32 projectId,
        uint256 amount,
        uint256 deadlineOffset
    ) internal returns (bytes32 grantId) {
        vm.startPrank(grantor);
        token.approve(address(disburse), amount);
        grantId = disburse.commitGrant(
            beneficiary,
            address(token),
            amount,
            hash,
            block.timestamp + deadlineOffset,
            projectId,
            0
        );
        vm.stopPrank();
    }

    function test_fullFlow_commitAttestedClaim() public {
        _attest(compHash, projectBankit);
        bytes32 grantId = _commit(compHash, projectBankit, 50_000e18, 30 days);

        uint256 balBefore = token.balanceOf(beneficiary);
        vm.prank(beneficiary);
        disburse.claimGrant(grantId);

        assertEq(token.balanceOf(beneficiary) - balBefore, 50_000e18);
        assertTrue(disburse.getGrant(grantId).claimed);
        assertEq(token.balanceOf(address(disburse)), 0); // contract holds nothing after claim
    }

    function test_revert_claimWithoutAttestation() public {
        bytes32 grantId = _commit(compHash, projectBankit, 50_000e18, 30 days);

        vm.prank(beneficiary);
        vm.expectRevert("AtomicDisbursement: compliance not attested");
        disburse.claimGrant(grantId);
    }

    function test_revert_claimAfterDeadline() public {
        _attest(compHash, projectBankit);
        bytes32 grantId = _commit(compHash, projectBankit, 50_000e18, 1 days);

        vm.warp(block.timestamp + 2 days);

        vm.prank(beneficiary);
        vm.expectRevert("AtomicDisbursement: expired");
        disburse.claimGrant(grantId);
    }

    function test_revert_attackerCannotClaim() public {
        _attest(compHash, projectBankit);
        bytes32 grantId = _commit(compHash, projectBankit, 50_000e18, 30 days);

        vm.prank(attacker);
        vm.expectRevert("AtomicDisbursement: not beneficiary");
        disburse.claimGrant(grantId);
    }

    function test_revert_doubleClaim() public {
        _attest(compHash, projectBankit);
        bytes32 grantId = _commit(compHash, projectBankit, 50_000e18, 30 days);

        vm.prank(beneficiary);
        disburse.claimGrant(grantId);

        vm.prank(beneficiary);
        vm.expectRevert("AtomicDisbursement: already claimed");
        disburse.claimGrant(grantId);
    }

    function test_grantorCancel_afterDeadline() public {
        bytes32 grantId = _commit(compHash, projectBankit, 50_000e18, 1 days);
        vm.warp(block.timestamp + 2 days);

        uint256 balBefore = token.balanceOf(grantor);
        vm.prank(grantor);
        disburse.cancelGrant(grantId);

        assertGt(token.balanceOf(grantor), balBefore);
        assertTrue(disburse.getGrant(grantId).cancelled);
        assertEq(token.balanceOf(address(disburse)), 0);
    }

    function test_revert_cancelBeforeDeadline() public {
        bytes32 grantId = _commit(compHash, projectBankit, 50_000e18, 30 days);

        vm.prank(grantor);
        vm.expectRevert("AtomicDisbursement: deadline not passed");
        disburse.cancelGrant(grantId);
    }

    function test_revert_cancelClaimedGrant() public {
        _attest(compHash, projectBankit);
        bytes32 grantId = _commit(compHash, projectBankit, 50_000e18, 30 days);

        vm.prank(beneficiary);
        disburse.claimGrant(grantId);

        vm.warp(block.timestamp + 31 days);
        vm.prank(grantor);
        vm.expectRevert("AtomicDisbursement: already claimed");
        disburse.cancelGrant(grantId);
    }

    function test_revokedAttestation_blocksClaim() public {
        _attest(compHash, projectBankit);
        bytes32 grantId = _commit(compHash, projectBankit, 50_000e18, 30 days);

        vm.prank(admin);
        compliance.revoke(compHash);

        vm.prank(beneficiary);
        vm.expectRevert("AtomicDisbursement: compliance not attested");
        disburse.claimGrant(grantId);
    }

    function test_multiProject_independentGrants() public {
        bytes32 hash2 = keccak256("nsfi-brf-001");
        _attest(compHash, projectBankit);
        _attest(hash2,    projectBRF);

        bytes32 grantId1 = _commit(compHash, projectBankit, 50_000e18, 30 days);
        bytes32 grantId2 = _commit(hash2,    projectBRF,    25_000e18, 60 days);

        vm.prank(beneficiary);
        disburse.claimGrant(grantId1);

        // grantId2 still claimable
        AtomicDisbursement.Grant memory g2 = disburse.getGrant(grantId2);
        assertFalse(g2.claimed);

        vm.prank(beneficiary);
        disburse.claimGrant(grantId2);

        assertEq(token.balanceOf(beneficiary), 75_000e18);
    }

    function test_updateComplianceRegistry() public {
        ComplianceAttestation newReg = new ComplianceAttestation(admin);

        vm.prank(admin);
        disburse.updateComplianceRegistry(address(newReg));

        assertEq(address(disburse.complianceRegistry()), address(newReg));
    }
}
