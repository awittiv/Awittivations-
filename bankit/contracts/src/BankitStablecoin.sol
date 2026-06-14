// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/// @title BankitStablecoin — Bankit Dollar (BKD)
/// @notice Implements the Atomic Cash-to-Mint (ACM) Protocol.
///         Only the BankitLiquidityRouter (ROUTER_ROLE) can mint or burn.
///         6 decimals — 1 BKD = 1 INR, matching backend's 10^6 unit scaling.
contract BankitStablecoin is ERC20, AccessControl, Pausable {
    bytes32 public constant ROUTER_ROLE = keccak256("ROUTER_ROLE");
    bytes32 public constant COMPLIANCE_ROLE = keccak256("COMPLIANCE_ROLE");

    event AtomicMint(address indexed to, uint256 amount, string referenceId);
    event AtomicBurn(address indexed from, uint256 amount, string referenceId);

    constructor(address admin) ERC20("Bankit Dollar", "BKD") {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(COMPLIANCE_ROLE, admin);
    }

    /// @dev 6 decimals so 1_000_000 = ₹1. Matches backend: int(amount_inr * 10**6).
    function decimals() public pure override returns (uint8) {
        return 6;
    }

    /// @notice Mint BKD to a recipient after a verified loan disbursement.
    function mint(address to, uint256 amount, string calldata referenceId)
        external
        onlyRole(ROUTER_ROLE)
        whenNotPaused
    {
        _mint(to, amount);
        emit AtomicMint(to, amount, referenceId);
    }

    /// @notice Burn BKD from an address when a loan is repaid.
    function burn(address from, uint256 amount, string calldata referenceId)
        external
        onlyRole(ROUTER_ROLE)
    {
        _burn(from, amount);
        emit AtomicBurn(from, amount, referenceId);
    }

    function pause() external onlyRole(COMPLIANCE_ROLE) { _pause(); }
    function unpause() external onlyRole(COMPLIANCE_ROLE) { _unpause(); }
}
