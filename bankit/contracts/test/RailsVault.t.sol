// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/RailsVault.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockToken is ERC20 {
    constructor() ERC20("MockToken", "MCK") {
        _mint(msg.sender, 1_000_000e18);
    }
}

contract RailsVaultTest is Test {
    RailsVault vault;
    MockToken  token;

    uint256 ownerKey  = 0xA11CE;
    address owner     = vm.addr(0xA11CE);
    address recipient = makeAddr("recipient");
    address relayer   = makeAddr("relayer");

    function setUp() public {
        vault = new RailsVault();
        token = new MockToken();
        token.transfer(owner, 100_000e18);
    }

    function _deposit(uint256 amount) internal {
        vm.startPrank(owner);
        token.approve(address(vault), amount);
        vault.deposit(address(token), amount, keccak256("bankit"));
        vm.stopPrank();
    }

    function _buildPermit(
        uint256 amount,
        address _recipient,
        uint256 deadline
    ) internal view returns (bytes memory sig) {
        uint256 nonce = vault.nonces(owner);
        bytes32 structHash = keccak256(abi.encode(
            vault.WITHDRAW_TYPEHASH(),
            owner,
            address(token),
            amount,
            _recipient,
            nonce,
            deadline
        ));
        bytes32 digest = vault.hashTypedDataV4(structHash);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(ownerKey, digest);
        sig = abi.encodePacked(r, s, v);
    }

    function test_deposit() public {
        _deposit(1_000e18);
        assertEq(vault.balanceOf(owner, address(token)), 1_000e18);
    }

    function test_directWithdraw() public {
        _deposit(1_000e18);
        vm.prank(owner);
        vault.withdraw(address(token), 600e18, recipient, keccak256("bankit"));
        assertEq(vault.balanceOf(owner, address(token)), 400e18);
        assertEq(token.balanceOf(recipient), 600e18);
    }

    function test_withdrawWithPermit_byOwner() public {
        _deposit(1_000e18);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _buildPermit(500e18, recipient, deadline);

        vm.prank(owner);
        vault.withdrawWithPermit(owner, address(token), 500e18, recipient, deadline, sig);

        assertEq(vault.balanceOf(owner, address(token)), 500e18);
        assertEq(token.balanceOf(recipient), 500e18);
    }

    function test_withdrawWithPermit_byRelayer() public {
        _deposit(1_000e18);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _buildPermit(500e18, recipient, deadline);

        // Relayer submits on behalf of owner — funds still go to recipient, not relayer
        vm.prank(relayer);
        vault.withdrawWithPermit(owner, address(token), 500e18, recipient, deadline, sig);

        assertEq(vault.balanceOf(owner, address(token)), 500e18);
        assertEq(token.balanceOf(recipient), 500e18);
        assertEq(token.balanceOf(relayer), 0); // relayer gets nothing
    }

    function test_revert_expiredPermit() public {
        _deposit(1_000e18);
        uint256 deadline = block.timestamp - 1;
        bytes memory sig = _buildPermit(500e18, recipient, deadline);

        vm.expectRevert("RailsVault: permit expired");
        vault.withdrawWithPermit(owner, address(token), 500e18, recipient, deadline, sig);
    }

    function test_revert_wrongSigner() public {
        _deposit(1_000e18);
        uint256 deadline = block.timestamp + 1 hours;
        uint256 nonce = vault.nonces(owner);
        bytes32 structHash = keccak256(abi.encode(
            vault.WITHDRAW_TYPEHASH(), owner, address(token),
            uint256(500e18), recipient, nonce, deadline
        ));
        bytes32 digest = vault.hashTypedDataV4(structHash);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(0xBAD, digest); // wrong key

        vm.expectRevert("RailsVault: invalid signature");
        vault.withdrawWithPermit(owner, address(token), 500e18, recipient, deadline, abi.encodePacked(r, s, v));
    }

    function test_revert_replayAttack() public {
        _deposit(1_000e18);
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory sig = _buildPermit(500e18, recipient, deadline);

        vm.prank(owner);
        vault.withdrawWithPermit(owner, address(token), 500e18, recipient, deadline, sig);

        // replay same sig — nonce has incremented, must fail
        vm.expectRevert("RailsVault: invalid signature");
        vault.withdrawWithPermit(owner, address(token), 500e18, recipient, deadline, sig);
    }

    function test_revert_insufficientBalance() public {
        vm.prank(owner);
        vm.expectRevert("RailsVault: insufficient balance");
        vault.withdraw(address(token), 1e18, recipient, bytes32(0));
    }

    function test_multipleOwners_isolated() public {
        address alice = makeAddr("alice");
        address bob   = makeAddr("bob");
        token.transfer(alice, 5_000e18);
        token.transfer(bob,   5_000e18);

        vm.startPrank(alice);
        token.approve(address(vault), 5_000e18);
        vault.deposit(address(token), 5_000e18, keccak256("brf"));
        vm.stopPrank();

        vm.startPrank(bob);
        token.approve(address(vault), 3_000e18);
        vault.deposit(address(token), 3_000e18, keccak256("launchlayer"));
        vm.stopPrank();

        assertEq(vault.balanceOf(alice, address(token)), 5_000e18);
        assertEq(vault.balanceOf(bob,   address(token)), 3_000e18);

        // bob cannot touch alice's balance
        vm.prank(bob);
        vm.expectRevert("RailsVault: insufficient balance");
        vault.withdraw(address(token), 5_000e18, bob, bytes32(0));
    }
}
