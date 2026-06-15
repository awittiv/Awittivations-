// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";

/// @title ComplianceAttestation
/// @notice On-chain registry for SBA and RBI NSFI 2025-30 compliance records.
/// Authorized attesters write records; records gate grant releases in AtomicDisbursement.
/// Program types: 0=SBA_7A, 1=SBA_SBLC, 2=SBA_MADE_IN_AMERICA, 3=SBA_EIDL, 4=SBA_MICROLOAN, 5=NSFI
/// NSFI pillars: 0=NONE, 1=UNIVERSAL_ACCESS, 2=GENDER_INCLUSION, 3=LIVELIHOOD_LINKAGES, 4=FINANCIAL_LITERACY, 5=CUSTOMER_PROTECTION
contract ComplianceAttestation is AccessControl {
    bytes32 public constant ATTESTER_ROLE = keccak256("ATTESTER_ROLE");

    struct Attestation {
        bytes32 complianceHash;
        bytes32 projectId;
        uint8   programType;
        uint8   nsfiPillar;
        string  applicationRef;
        uint256 amountUSDCents;
        uint256 attestedAt;
        address attester;
        bool    active;
    }

    mapping(bytes32 => Attestation) public attestations;
    mapping(bytes32 => bytes32[]) public projectAttestations;

    event AttestationRecorded(
        bytes32 indexed complianceHash,
        bytes32 indexed projectId,
        uint8 programType,
        address attester
    );
    event AttestationRevoked(bytes32 indexed complianceHash, address revoker);

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ATTESTER_ROLE, admin);
    }

    /// @notice Record a compliance attestation for an approved SBA or NSFI grant.
    function attest(
        bytes32 complianceHash,
        bytes32 projectId,
        uint8   programType,
        uint8   nsfiPillar,
        string calldata applicationRef,
        uint256 amountUSDCents
    ) external onlyRole(ATTESTER_ROLE) {
        require(!attestations[complianceHash].active, "ComplianceAttestation: already attested");

        attestations[complianceHash] = Attestation({
            complianceHash:  complianceHash,
            projectId:       projectId,
            programType:     programType,
            nsfiPillar:      nsfiPillar,
            applicationRef:  applicationRef,
            amountUSDCents:  amountUSDCents,
            attestedAt:      block.timestamp,
            attester:        msg.sender,
            active:          true
        });

        projectAttestations[projectId].push(complianceHash);

        emit AttestationRecorded(complianceHash, projectId, programType, msg.sender);
    }

    /// @notice Revoke a previously active attestation (e.g., SBA application rejected).
    function revoke(bytes32 complianceHash) external onlyRole(ATTESTER_ROLE) {
        require(attestations[complianceHash].active, "ComplianceAttestation: not active");
        attestations[complianceHash].active = false;
        emit AttestationRevoked(complianceHash, msg.sender);
    }

    /// @notice Returns true if the hash is attested and active. Called by AtomicDisbursement.
    function isAttested(bytes32 complianceHash) external view returns (bool) {
        return attestations[complianceHash].active;
    }

    function getAttestation(bytes32 complianceHash) external view returns (Attestation memory) {
        return attestations[complianceHash];
    }

    function getProjectAttestations(bytes32 projectId) external view returns (bytes32[] memory) {
        return projectAttestations[projectId];
    }
}
