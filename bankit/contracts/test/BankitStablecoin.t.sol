// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/BankitStablecoin.sol";

contract BankitStablecoinTest is Test {
    event AtomicMint(address indexed to, uint256 amount, string referenceId);
    event AtomicBurn(address indexed from, uint256 amount, string referenceId);

    BankitStablecoin public token;

    address public admin    = address(1);
    address public router   = address(2);
    address public user     = address(3);
    address public attacker = address(4);

    function setUp() public {
        token = new BankitStablecoin(admin);
        bytes32 routerRole = token.ROUTER_ROLE();
        vm.prank(admin);
        token.grantRole(routerRole, router);
    }

    // ── Metadata ──────────────────────────────────────────────────────────────

    function test_Metadata() public view {
        assertEq(token.name(), "Bankit Dollar");
        assertEq(token.symbol(), "BKD");
        assertEq(token.decimals(), 6);
    }

    // ── Mint ──────────────────────────────────────────────────────────────────

    function test_RouterCanMint() public {
        vm.prank(router);
        token.mint(user, 5_000_000, "loan_abc"); // ₹5 in 6-decimal units
        assertEq(token.balanceOf(user), 5_000_000);
    }

    function test_MintRevertsForNonRouter() public {
        vm.prank(attacker);
        vm.expectRevert();
        token.mint(user, 5_000_000, "loan_abc");
    }

    function test_MintEmitsAtomicMint() public {
        vm.prank(router);
        vm.expectEmit(true, false, false, true);
        emit AtomicMint(user, 5_000_000, "loan_abc");
        token.mint(user, 5_000_000, "loan_abc");
    }

    // ── Burn ──────────────────────────────────────────────────────────────────

    function test_RouterCanBurn() public {
        vm.prank(router);
        token.mint(user, 5_000_000, "loan_abc");
        vm.prank(router);
        token.burn(user, 5_000_000, "repay_abc");
        assertEq(token.balanceOf(user), 0);
    }

    function test_BurnRevertsForNonRouter() public {
        vm.prank(router);
        token.mint(user, 5_000_000, "loan_abc");
        vm.prank(attacker);
        vm.expectRevert();
        token.burn(user, 5_000_000, "repay_abc");
    }

    function test_BurnEmitsAtomicBurn() public {
        vm.prank(router);
        token.mint(user, 5_000_000, "loan_abc");
        vm.prank(router);
        vm.expectEmit(true, false, false, true);
        emit AtomicBurn(user, 5_000_000, "repay_abc");
        token.burn(user, 5_000_000, "repay_abc");
    }

    // ── Pause ─────────────────────────────────────────────────────────────────

    function test_PauseBlocksMint() public {
        vm.prank(admin);
        token.pause();
        vm.prank(router);
        vm.expectRevert();
        token.mint(user, 5_000_000, "loan_abc");
    }

    function test_UnpauseRestoresMint() public {
        vm.prank(admin);
        token.pause();
        vm.prank(admin);
        token.unpause();
        vm.prank(router);
        token.mint(user, 5_000_000, "loan_abc");
        assertEq(token.balanceOf(user), 5_000_000);
    }

    function test_PauseRevertsForNonCompliance() public {
        vm.prank(attacker);
        vm.expectRevert();
        token.pause();
    }

    // ── Fuzz ──────────────────────────────────────────────────────────────────

    function testFuzz_MintAndBurn(uint96 amount) public {
        vm.assume(amount > 0);
        vm.startPrank(router);
        token.mint(user, amount, "ref");
        assertEq(token.balanceOf(user), amount);
        token.burn(user, amount, "ref");
        assertEq(token.balanceOf(user), 0);
        vm.stopPrank();
    }
}
