// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/BankitCreditPassport.sol";

contract BankitCreditPassportTest is Test {
    BankitCreditPassport passport;

    address admin   = address(0xA0);
    address oracle  = address(0xA1);
    address merchant = address(0xB0);
    address stranger = address(0xC0);

    string constant MERCHANT_ID = "550e8400-e29b-41d4-a716-446655440000";

    bytes32 constant ORACLE_ROLE = keccak256("ORACLE_ROLE");

    function setUp() public {
        passport = new BankitCreditPassport(admin);
        vm.prank(admin);
        passport.grantRole(ORACLE_ROLE, oracle);
    }

    // ── Minting ──────────────────────────────────────────────────────────────

    function test_MintPassportEmitsEvent() public {
        vm.expectEmit(true, true, false, true);
        emit BankitCreditPassport.PassportMinted(1, merchant, MERCHANT_ID);
        vm.prank(oracle);
        passport.mintPassport(merchant, MERCHANT_ID, 72);
    }

    function test_MintPassportEmitsLocked() public {
        vm.expectEmit(false, false, false, true);
        emit IERC5192.Locked(1);
        vm.prank(oracle);
        passport.mintPassport(merchant, MERCHANT_ID, 72);
    }

    function test_MintSetsProfile() public {
        vm.prank(oracle);
        uint256 tokenId = passport.mintPassport(merchant, MERCHANT_ID, 72);

        (
            uint8 score,
            uint32 repaid,
            uint32 total,
            uint96 repaidUnits,
            uint64 since,
            string memory id
        ) = passport.profiles(tokenId);

        assertEq(score,      72);
        assertEq(repaid,     0);
        assertEq(total,      1);
        assertEq(repaidUnits, 0);
        assertTrue(since > 0);
        assertEq(id,         MERCHANT_ID);
    }

    function test_MintRegistersLookups() public {
        vm.prank(oracle);
        uint256 tokenId = passport.mintPassport(merchant, MERCHANT_ID, 72);

        assertEq(passport.merchantTokenId(MERCHANT_ID), tokenId);
        assertEq(passport.walletTokenId(merchant),      tokenId);
    }

    function test_MintRevertsForNonOracle() public {
        vm.prank(stranger);
        vm.expectRevert();
        passport.mintPassport(merchant, MERCHANT_ID, 72);
    }

    function test_MintRevertsOnDuplicate() public {
        vm.startPrank(oracle);
        passport.mintPassport(merchant, MERCHANT_ID, 72);
        vm.expectRevert("Passport already exists");
        passport.mintPassport(merchant, MERCHANT_ID, 80);
        vm.stopPrank();
    }

    // ── Soulbound enforcement ────────────────────────────────────────────────

    function test_TransferReverts() public {
        vm.prank(oracle);
        uint256 tokenId = passport.mintPassport(merchant, MERCHANT_ID, 72);

        vm.prank(merchant);
        vm.expectRevert("BankitCreditPassport: soulbound token is non-transferable");
        passport.transferFrom(merchant, stranger, tokenId);
    }

    function test_LockedReturnsTrue() public {
        vm.prank(oracle);
        uint256 tokenId = passport.mintPassport(merchant, MERCHANT_ID, 72);
        assertTrue(passport.locked(tokenId));
    }

    // ── Credit profile updates ───────────────────────────────────────────────

    function test_UpdateScoreOnNewLoan() public {
        vm.startPrank(oracle);
        uint256 tokenId = passport.mintPassport(merchant, MERCHANT_ID, 60);
        passport.updateCreditProfile(MERCHANT_ID, 65, false, 0);
        vm.stopPrank();

        (uint8 score,,uint32 total,,,) = passport.profiles(tokenId);
        assertEq(score, 65);
        assertEq(total, 2);
    }

    function test_UpdateScoreOnRepayment() public {
        vm.startPrank(oracle);
        uint256 tokenId = passport.mintPassport(merchant, MERCHANT_ID, 60);
        passport.updateCreditProfile(MERCHANT_ID, 75, true, 5_000_000); // ₹5 repaid
        vm.stopPrank();

        (uint8 score, uint32 repaid,, uint96 repaidUnits,,) = passport.profiles(tokenId);
        assertEq(score,       75);
        assertEq(repaid,      1);
        assertEq(repaidUnits, 5_000_000);
    }

    function test_UpdateEmitsEvent() public {
        vm.startPrank(oracle);
        uint256 tokenId = passport.mintPassport(merchant, MERCHANT_ID, 60);
        vm.expectEmit(true, false, false, true);
        emit BankitCreditPassport.CreditProfileUpdated(tokenId, 80, 1);
        passport.updateCreditProfile(MERCHANT_ID, 80, true, 0);
        vm.stopPrank();
    }

    function test_UpdateRevertsForUnknownMerchant() public {
        vm.prank(oracle);
        vm.expectRevert("No passport found for merchant");
        passport.updateCreditProfile("nonexistent-id", 80, false, 0);
    }

    // ── DeFi composability ───────────────────────────────────────────────────

    function test_CreditScoreQuery() public {
        vm.prank(oracle);
        passport.mintPassport(merchant, MERCHANT_ID, 72);
        assertEq(passport.creditScore(merchant), 72);
    }

    function test_HasPassport() public {
        assertFalse(passport.hasPassport(merchant));
        vm.prank(oracle);
        passport.mintPassport(merchant, MERCHANT_ID, 72);
        assertTrue(passport.hasPassport(merchant));
    }

    function test_CreditScoreRevertsWithoutPassport() public {
        vm.expectRevert("No passport for this wallet");
        passport.creditScore(stranger);
    }

    // ── Token URI / metadata ─────────────────────────────────────────────────

    function test_TokenURIReturnsBase64Json() public {
        vm.prank(oracle);
        uint256 tokenId = passport.mintPassport(merchant, MERCHANT_ID, 72);
        string memory uri = passport.tokenURI(tokenId);
        // Verify it starts with "data:application/json;base64,"
        bytes memory b = bytes(uri);
        assertEq(b[0], bytes("d")[0]); // d
        assertEq(b[1], bytes("a")[0]); // a
        assertEq(b[2], bytes("t")[0]); // t
        assertEq(b[3], bytes("a")[0]); // a
        assertEq(b[4], bytes(":")[0]); // :
    }

    function test_TokenURIRevertsForNonexistentToken() public {
        vm.expectRevert("Token does not exist");
        passport.tokenURI(999);
    }

    // ── ERC-165 interface support ────────────────────────────────────────────

    function test_SupportsERC5192() public view {
        assertTrue(passport.supportsInterface(type(IERC5192).interfaceId));
    }

    function test_SupportsERC721() public view {
        assertTrue(passport.supportsInterface(0x80ac58cd)); // ERC-721
    }

    // ── Fuzz ─────────────────────────────────────────────────────────────────

    function testFuzz_ScoreClamped(uint8 rawScore) public {
        vm.prank(oracle);
        uint256 tokenId = passport.mintPassport(merchant, MERCHANT_ID, rawScore);
        (uint8 score,,,,,) = passport.profiles(tokenId);
        // score should be stored exactly (uint8 is already 0-255; contract stores it as-is)
        assertEq(score, rawScore);
    }
}
