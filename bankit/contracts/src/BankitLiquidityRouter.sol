// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "./BankitStablecoin.sol";

/// @title BankitLiquidityRouter
/// @notice Orchestrates BKD mint/burn for loan disbursements and repayments.
///         The backend oracle wallet holds ORACLE_ROLE and calls this contract.
///         All on-chain actions are logged in ais_program_audit for regulatory
///         compliance with Michigan Bulletin 2026-03-BT.
contract BankitLiquidityRouter is AccessControl {
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");

    BankitStablecoin public immutable stablecoin;

    struct AuditEntry {
        address recipient;
        uint256 amount;
        string trustScoreHash;
        uint256 timestamp;
    }

    /// @notice On-chain audit ledger: trustScoreHash → audit entry.
    mapping(string => AuditEntry) public ais_program_audit;

    event MicroLiquidityReleased(
        address indexed recipient,
        uint256 fiatAmount,
        string trustScoreHash
    );
    event LoanRepaid(
        address indexed from,
        uint256 fiatAmount,
        string loanId
    );

    constructor(address stablecoinAddress, address admin) {
        stablecoin = BankitStablecoin(stablecoinAddress);
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ORACLE_ROLE, admin);
    }

    /// @notice Disburse a micro-loan: mint BKD to recipient's wallet.
    /// @param recipientWallet  Merchant's Polygon wallet.
    /// @param fiatAmount       Amount in 6-decimal BKD units (= amount_inr * 10^6).
    /// @param trustScoreHash   SHA-256 of (loan_id:score:reasoning) from the AI pipeline.
    function releaseMicroLiquidity(
        address recipientWallet,
        uint256 fiatAmount,
        string calldata trustScoreHash
    ) external onlyRole(ORACLE_ROLE) {
        ais_program_audit[trustScoreHash] = AuditEntry({
            recipient: recipientWallet,
            amount: fiatAmount,
            trustScoreHash: trustScoreHash,
            timestamp: block.timestamp
        });

        stablecoin.mint(recipientWallet, fiatAmount, trustScoreHash);
        emit MicroLiquidityReleased(recipientWallet, fiatAmount, trustScoreHash);
    }

    /// @notice Record a loan repayment: burn BKD from merchant's wallet.
    /// @dev    Requires merchant to have approved this contract to spend their BKD.
    function repayLoan(
        address from,
        uint256 fiatAmount,
        string calldata loanId
    ) external onlyRole(ORACLE_ROLE) {
        stablecoin.burn(from, fiatAmount, loanId);
        emit LoanRepaid(from, fiatAmount, loanId);
    }

    /// @notice Authorize an additional oracle wallet (e.g. a new backend key rotation).
    function grantOracleRole(address account) external onlyRole(DEFAULT_ADMIN_ROLE) {
        _grantRole(ORACLE_ROLE, account);
    }

    /// @notice Revoke an oracle wallet (key rotation / incident response).
    function revokeOracleRole(address account) external onlyRole(DEFAULT_ADMIN_ROLE) {
        _revokeRole(ORACLE_ROLE, account);
    }
}
