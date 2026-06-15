// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title RailsVault
/// @notice Non-custodial vault for Awittivations projects.
/// Platform routes signed permits but NEVER controls funds.
/// Withdrawal requires the vault owner's own EIP-712 signature specifying
/// the recipient — even a relayer cannot redirect funds to a different address.
contract RailsVault is EIP712, ReentrancyGuard {
    using ECDSA for bytes32;
    using SafeERC20 for IERC20;

    bytes32 public constant WITHDRAW_TYPEHASH = keccak256(
        "Withdraw(address owner,address token,uint256 amount,address recipient,uint256 nonce,uint256 deadline)"
    );

    // owner => token => balance
    mapping(address => mapping(address => uint256)) public vaultBalance;
    // replay-protection nonce per owner
    mapping(address => uint256) public nonces;

    event Deposited(address indexed owner, address indexed token, uint256 amount, bytes32 indexed projectId);
    event Withdrawn(address indexed owner, address indexed token, uint256 amount, address recipient, bytes32 indexed projectId);

    constructor() EIP712("RailsVault", "1") {}

    /// @notice Deposit tokens into your own non-custodial vault slot.
    function deposit(address token, uint256 amount, bytes32 projectId) external nonReentrant {
        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);
        vaultBalance[msg.sender][token] += amount;
        emit Deposited(msg.sender, token, amount, projectId);
    }

    /// @notice Gasless withdrawal via EIP-712 permit signed offline by the vault owner.
    /// Anyone (including a platform relayer) may submit, but the owner's signature
    /// locks both the amount and recipient — funds cannot be redirected.
    function withdrawWithPermit(
        address owner,
        address token,
        uint256 amount,
        address recipient,
        uint256 deadline,
        bytes calldata signature
    ) external nonReentrant {
        require(block.timestamp <= deadline, "RailsVault: permit expired");

        uint256 nonce = nonces[owner]++;

        bytes32 structHash = keccak256(abi.encode(
            WITHDRAW_TYPEHASH,
            owner,
            token,
            amount,
            recipient,
            nonce,
            deadline
        ));

        address signer = _hashTypedDataV4(structHash).recover(signature);
        require(signer == owner, "RailsVault: invalid signature");
        require(vaultBalance[owner][token] >= amount, "RailsVault: insufficient balance");

        vaultBalance[owner][token] -= amount;
        IERC20(token).safeTransfer(recipient, amount);

        emit Withdrawn(owner, token, amount, recipient, bytes32(0));
    }

    /// @notice Direct withdrawal — vault owner calls themselves, no relayer needed.
    function withdraw(address token, uint256 amount, address recipient, bytes32 projectId) external nonReentrant {
        require(vaultBalance[msg.sender][token] >= amount, "RailsVault: insufficient balance");
        vaultBalance[msg.sender][token] -= amount;
        IERC20(token).safeTransfer(recipient, amount);
        emit Withdrawn(msg.sender, token, amount, recipient, projectId);
    }

    function balanceOf(address owner, address token) external view returns (uint256) {
        return vaultBalance[owner][token];
    }

    /// @dev Exposed for off-chain permit construction and testing.
    function hashTypedDataV4(bytes32 structHash) external view returns (bytes32) {
        return _hashTypedDataV4(structHash);
    }
}
