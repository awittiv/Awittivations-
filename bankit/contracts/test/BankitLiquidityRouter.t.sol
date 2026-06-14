// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/BankitStablecoin.sol";
import "../src/BankitLiquidityRouter.sol";

contract BankitLiquidityRouterTest is Test {
    event MicroLiquidityReleased(address indexed recipient, uint256 fiatAmount, string trustScoreHash);
    event LoanRepaid(address indexed from, uint256 fiatAmount, string loanId);

    BankitStablecoin public token;
    BankitLiquidityRouter public router;

    address public admin    = address(1);
    address public oracle   = address(2);
    address public merchant = address(3);
    address public attacker = address(4);

    function setUp() public {
        vm.startPrank(admin);
        token = new BankitStablecoin(admin);
        router = new BankitLiquidityRouter(address(token), admin);

        token.grantRole(token.ROUTER_ROLE(), address(router));
        router.grantOracleRole(oracle);
        vm.stopPrank();
    }

    // ── releaseMicroLiquidity ─────────────────────────────────────────────────

    function test_ReleaseMintsBKD() public {
        vm.prank(oracle);
        router.releaseMicroLiquidity(merchant, 5_000_000, "hash_abc");
        assertEq(token.balanceOf(merchant), 5_000_000);
    }

    function test_ReleaseWritesAuditEntry() public {
        vm.prank(oracle);
        router.releaseMicroLiquidity(merchant, 5_000_000, "hash_abc");

        (address rec, uint256 amt, string memory hash, uint256 ts) =
            router.ais_program_audit("hash_abc");

        assertEq(rec, merchant);
        assertEq(amt, 5_000_000);
        assertEq(hash, "hash_abc");
        assertGt(ts, 0);
    }

    function test_ReleaseEmitsEvent() public {
        vm.prank(oracle);
        vm.expectEmit(true, false, false, true);
        emit MicroLiquidityReleased(merchant, 5_000_000, "hash_abc");
        router.releaseMicroLiquidity(merchant, 5_000_000, "hash_abc");
    }

    function test_ReleaseRevertsForNonOracle() public {
        vm.prank(attacker);
        vm.expectRevert();
        router.releaseMicroLiquidity(merchant, 5_000_000, "hash_abc");
    }

    // ── repayLoan ─────────────────────────────────────────────────────────────

    function test_RepayBurnsBKD() public {
        vm.prank(oracle);
        router.releaseMicroLiquidity(merchant, 5_000_000, "hash_abc");
        assertEq(token.balanceOf(merchant), 5_000_000);

        vm.prank(oracle);
        router.repayLoan(merchant, 5_000_000, "loan_abc");
        assertEq(token.balanceOf(merchant), 0);
    }

    function test_RepayEmitsEvent() public {
        vm.prank(oracle);
        router.releaseMicroLiquidity(merchant, 5_000_000, "hash_abc");

        vm.prank(oracle);
        vm.expectEmit(true, false, false, true);
        emit LoanRepaid(merchant, 5_000_000, "loan_abc");
        router.repayLoan(merchant, 5_000_000, "loan_abc");
    }

    function test_RepayRevertsForNonOracle() public {
        vm.prank(oracle);
        router.releaseMicroLiquidity(merchant, 5_000_000, "hash_abc");

        vm.prank(attacker);
        vm.expectRevert();
        router.repayLoan(merchant, 5_000_000, "loan_abc");
    }

    // ── Role management ───────────────────────────────────────────────────────

    function test_AdminCanRevokeOracle() public {
        vm.prank(admin);
        router.revokeOracleRole(oracle);

        vm.prank(oracle);
        vm.expectRevert();
        router.releaseMicroLiquidity(merchant, 5_000_000, "hash");
    }

    function test_NonAdminCannotGrantOracle() public {
        vm.prank(attacker);
        vm.expectRevert();
        router.grantOracleRole(attacker);
    }

    // ── Fuzz ──────────────────────────────────────────────────────────────────

    function testFuzz_DisburseAndRepay(uint96 amount) public {
        vm.assume(amount > 0);
        vm.startPrank(oracle);
        router.releaseMicroLiquidity(merchant, amount, "hash");
        assertEq(token.balanceOf(merchant), amount);
        router.repayLoan(merchant, amount, "loan");
        assertEq(token.balanceOf(merchant), 0);
        vm.stopPrank();
    }
}
