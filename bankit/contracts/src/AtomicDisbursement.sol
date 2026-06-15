// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

interface IComplianceAttestation {
    function isAttested(bytes32 complianceHash) external view returns (bool);
}

/// @title AtomicDisbursement
/// @notice Trustless atomic grant/loan disbursement for SBA and NSFI-aligned funding.
/// Grantor deposits funds locked to a specific beneficiary.
/// Beneficiary claims directly — no platform key required, no intermediary custody.
/// Funds flow: grantor wallet → contract (escrow) → beneficiary wallet.
/// Platform NEVER possesses funds at any point.
contract AtomicDisbursement is ReentrancyGuard, Ownable {
    using SafeERC20 for IERC20;

    // Program types matching ComplianceAttestation
    uint8 public constant SBA_7A             = 0;
    uint8 public constant SBA_SBLC           = 1;
    uint8 public constant SBA_MADE_IN_AMERICA = 2;
    uint8 public constant SBA_EIDL           = 3;
    uint8 public constant SBA_MICROLOAN      = 4;
    uint8 public constant NSFI               = 5;

    struct Grant {
        address  grantor;
        address  beneficiary;
        address  token;
        uint256  amount;
        bytes32  complianceHash;
        uint256  deadline;
        bool     claimed;
        bool     cancelled;
        bytes32  projectId;
        uint8    programType;
    }

    IComplianceAttestation public complianceRegistry;

    mapping(bytes32 => Grant) public grants;
    uint256 public grantCount;

    event GrantCommitted(
        bytes32 indexed grantId,
        address indexed grantor,
        address indexed beneficiary,
        uint256 amount,
        bytes32 projectId,
        uint8 programType
    );
    event GrantClaimed(bytes32 indexed grantId, address indexed beneficiary, uint256 amount);
    event GrantCancelled(bytes32 indexed grantId, address indexed grantor, uint256 amount);

    constructor(address _complianceRegistry) Ownable(msg.sender) {
        complianceRegistry = IComplianceAttestation(_complianceRegistry);
    }

    /// @notice Grantor locks funds for a specific project + beneficiary.
    /// complianceHash must match an active ComplianceAttestation record at claim time.
    function commitGrant(
        address  beneficiary,
        address  token,
        uint256  amount,
        bytes32  complianceHash,
        uint256  deadline,
        bytes32  projectId,
        uint8    programType
    ) external nonReentrant returns (bytes32 grantId) {
        require(beneficiary != address(0), "AtomicDisbursement: zero beneficiary");
        require(amount > 0,                "AtomicDisbursement: zero amount");
        require(deadline > block.timestamp,"AtomicDisbursement: deadline in past");

        grantId = keccak256(abi.encodePacked(
            msg.sender, beneficiary, projectId, grantCount++
        ));

        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);

        grants[grantId] = Grant({
            grantor:        msg.sender,
            beneficiary:    beneficiary,
            token:          token,
            amount:         amount,
            complianceHash: complianceHash,
            deadline:       deadline,
            claimed:        false,
            cancelled:      false,
            projectId:      projectId,
            programType:    programType
        });

        emit GrantCommitted(grantId, msg.sender, beneficiary, amount, projectId, programType);
    }

    /// @notice Beneficiary claims their grant directly. Trustless — no platform key needed.
    /// Requires a valid on-chain compliance attestation matching the complianceHash.
    function claimGrant(bytes32 grantId) external nonReentrant {
        Grant storage g = grants[grantId];
        require(msg.sender == g.beneficiary,                       "AtomicDisbursement: not beneficiary");
        require(!g.claimed,                                        "AtomicDisbursement: already claimed");
        require(!g.cancelled,                                      "AtomicDisbursement: cancelled");
        require(block.timestamp <= g.deadline,                     "AtomicDisbursement: expired");
        require(complianceRegistry.isAttested(g.complianceHash),   "AtomicDisbursement: compliance not attested");

        g.claimed = true;
        IERC20(g.token).safeTransfer(g.beneficiary, g.amount);

        emit GrantClaimed(grantId, g.beneficiary, g.amount);
    }

    /// @notice Grantor reclaims funds if deadline passes without a claim.
    function cancelGrant(bytes32 grantId) external nonReentrant {
        Grant storage g = grants[grantId];
        require(msg.sender == g.grantor,   "AtomicDisbursement: not grantor");
        require(!g.claimed,                "AtomicDisbursement: already claimed");
        require(!g.cancelled,              "AtomicDisbursement: already cancelled");
        require(block.timestamp > g.deadline, "AtomicDisbursement: deadline not passed");

        g.cancelled = true;
        IERC20(g.token).safeTransfer(g.grantor, g.amount);

        emit GrantCancelled(grantId, g.grantor, g.amount);
    }

    function getGrant(bytes32 grantId) external view returns (Grant memory) {
        return grants[grantId];
    }

    function updateComplianceRegistry(address newRegistry) external onlyOwner {
        complianceRegistry = IComplianceAttestation(newRegistry);
    }
}
