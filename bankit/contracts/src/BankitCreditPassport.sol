// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Base64.sol";
import "@openzeppelin/contracts/utils/Strings.sol";

/// @dev ERC-5192: Minimal Soulbound Token interface
interface IERC5192 {
    event Locked(uint256 tokenId);
    function locked(uint256 tokenId) external view returns (bool);
}

/// @title BankitCreditPassport
/// @notice Soulbound NFT (ERC-5192) representing a merchant's AI-attested credit identity.
///         Minted on first loan approval. Non-transferable. Oracle updates score after
///         each loan lifecycle event. Dynamic on-chain SVG reflects live credit profile.
///         Composable: any DeFi protocol can query creditScore(wallet) for underwriting.
contract BankitCreditPassport is ERC721, AccessControl, IERC5192 {
    using Strings for uint256;

    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");

    uint256 private _nextTokenId = 1;

    struct CreditProfile {
        uint8  creditScore;           // 0–100, AI-attested
        uint32 loansRepaid;
        uint32 loansTotal;
        uint96 totalRepaidUnits;      // BKD units (6 decimals = ₹ * 10^6)
        uint64 memberSince;           // unix timestamp
        string merchantId;            // off-chain Supabase UUID
    }

    mapping(uint256  => CreditProfile) public profiles;
    mapping(string   => uint256)       public merchantTokenId;  // merchantId → tokenId
    mapping(address  => uint256)       public walletTokenId;    // wallet     → tokenId

    event CreditProfileUpdated(uint256 indexed tokenId, uint8 newScore, uint32 loansRepaid);
    event PassportMinted(uint256 indexed tokenId, address indexed wallet, string merchantId);

    constructor(address admin) ERC721("Bankit Credit Passport", "BCP") {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ORACLE_ROLE, admin);
    }

    // ── Oracle actions ───────────────────────────────────────────────────────

    /// @notice Mint a soulbound passport to a merchant's wallet on first approval.
    function mintPassport(
        address merchantWallet,
        string calldata merchantId,
        uint8  initialScore
    ) external onlyRole(ORACLE_ROLE) returns (uint256 tokenId) {
        require(merchantTokenId[merchantId] == 0, "Passport already exists");
        tokenId = _nextTokenId++;
        _mint(merchantWallet, tokenId);
        profiles[tokenId] = CreditProfile({
            creditScore:      initialScore,
            loansRepaid:      0,
            loansTotal:       1,
            totalRepaidUnits: 0,
            memberSince:      uint64(block.timestamp),
            merchantId:       merchantId
        });
        merchantTokenId[merchantId]   = tokenId;
        walletTokenId[merchantWallet] = tokenId;
        emit Locked(tokenId);
        emit PassportMinted(tokenId, merchantWallet, merchantId);
    }

    /// @notice Update credit profile after a loan event.
    /// @param loanRepaid  true = repayment event; false = new loan originated.
    /// @param repaidUnits BKD amount repaid (0 when loanRepaid=false).
    function updateCreditProfile(
        string calldata merchantId,
        uint8  newScore,
        bool   loanRepaid,
        uint96 repaidUnits
    ) external onlyRole(ORACLE_ROLE) {
        uint256 tokenId = merchantTokenId[merchantId];
        require(tokenId != 0, "No passport found for merchant");
        CreditProfile storage p = profiles[tokenId];
        p.creditScore = newScore;
        if (loanRepaid) {
            p.loansRepaid      += 1;
            p.totalRepaidUnits += repaidUnits;
        } else {
            p.loansTotal += 1;
        }
        emit CreditProfileUpdated(tokenId, newScore, p.loansRepaid);
    }

    // ── DeFi composability ───────────────────────────────────────────────────

    /// @notice Query credit score by wallet — readable by any external protocol.
    function creditScore(address wallet) external view returns (uint8) {
        uint256 tokenId = walletTokenId[wallet];
        require(tokenId != 0, "No passport for this wallet");
        return profiles[tokenId].creditScore;
    }

    /// @notice Check whether a wallet holds a verified Bankit passport.
    function hasPassport(address wallet) external view returns (bool) {
        return walletTokenId[wallet] != 0;
    }

    // ── ERC-5192: soulbound enforcement ─────────────────────────────────────

    /// @notice All tokens are permanently locked — soulbound.
    function locked(uint256) external pure override returns (bool) {
        return true;
    }

    /// @dev Block all transfers; allow only minting (from == address(0)).
    function _update(address to, uint256 tokenId, address auth)
        internal override returns (address)
    {
        address from = _ownerOf(tokenId);
        if (from != address(0) && to != address(0)) {
            revert("BankitCreditPassport: soulbound token is non-transferable");
        }
        return super._update(to, tokenId, auth);
    }

    // ── Dynamic on-chain metadata ────────────────────────────────────────────

    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        require(_ownerOf(tokenId) != address(0), "Token does not exist");
        CreditProfile memory p = profiles[tokenId];

        string memory svg  = _buildSVG(p, tokenId);
        string memory json = string(abi.encodePacked(
            '{"name":"Bankit Credit Passport #', tokenId.toString(), '",',
            '"description":"AI-attested, non-transferable on-chain credit identity for Bankit merchants. Score updates with every loan repayment.",',
            '"attributes":[',
                '{"trait_type":"Credit Score","value":',    uint256(p.creditScore).toString(),  '},',
                '{"trait_type":"Loans Repaid","value":',    uint256(p.loansRepaid).toString(),  '},',
                '{"trait_type":"Loans Total","value":',     uint256(p.loansTotal).toString(),   '},',
                '{"trait_type":"Soulbound","value":"Yes"},',
                '{"trait_type":"Merchant ID","value":"',    p.merchantId,                        '"}',
            '],',
            '"image":"data:image/svg+xml;base64,', Base64.encode(bytes(svg)), '"}'
        ));
        return string(abi.encodePacked(
            "data:application/json;base64,", Base64.encode(bytes(json))
        ));
    }

    function _buildSVG(CreditProfile memory p, uint256 tokenId)
        internal pure returns (string memory)
    {
        string memory scoreColor =
            p.creditScore >= 65 ? "#22c55e" :
            p.creditScore >= 40 ? "#f59e0b" : "#ef4444";

        string memory tier =
            p.creditScore >= 65 ? "PRIME" :
            p.creditScore >= 40 ? "STANDARD" : "SUBPRIME";

        string memory repaidStr = string(abi.encodePacked(
            uint256(p.loansRepaid).toString(), "/", uint256(p.loansTotal).toString()
        ));

        return string(abi.encodePacked(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 260">',
            '<defs>',
              '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
                '<stop offset="0%" stop-color="#0f172a"/>',
                '<stop offset="100%" stop-color="#1e3a5f"/>',
              '</linearGradient>',
              '<linearGradient id="bar" x1="0" y1="0" x2="1" y2="0">',
                '<stop offset="0%" stop-color="', scoreColor, '"/>',
                '<stop offset="100%" stop-color="', scoreColor, '" stop-opacity="0.4"/>',
              '</linearGradient>',
            '</defs>',
            '<rect width="420" height="260" rx="18" fill="url(#bg)"/>',
            // Header
            '<text x="22" y="38" font-family="monospace" font-size="11" fill="#64748b" letter-spacing="2">BANKIT CREDIT PASSPORT</text>',
            '<text x="22" y="58" font-family="monospace" font-size="10" fill="#334155">#', tokenId.toString(), '  |  AI-ATTESTED  |  SOULBOUND</text>',
            // Divider
            '<rect x="22" y="66" width="376" height="1" fill="#1e3a5f"/>',
            // Score
            '<text x="22" y="128" font-family="monospace" font-size="64" font-weight="bold" fill="', scoreColor, '">', uint256(p.creditScore).toString(), '</text>',
            '<text x="118" y="115" font-family="monospace" font-size="11" fill="#94a3b8">/100</text>',
            '<text x="118" y="132" font-family="monospace" font-size="11" fill="', scoreColor, '">', tier, '</text>',
            // Score bar
            '<rect x="22" y="145" width="376" height="6" rx="3" fill="#1e293b"/>',
            '<rect x="22" y="145" width="', _scaleBar(p.creditScore), '" height="6" rx="3" fill="url(#bar)"/>',
            // Stats
            '<text x="22"  y="178" font-family="monospace" font-size="11" fill="#94a3b8">LOANS REPAID</text>',
            '<text x="22"  y="196" font-family="monospace" font-size="16" fill="#e2e8f0">', repaidStr, '</text>',
            '<text x="180" y="178" font-family="monospace" font-size="11" fill="#94a3b8">TOTAL REPAID</text>',
            '<text x="180" y="196" font-family="monospace" font-size="16" fill="#e2e8f0">BKD ', _formatUnits(p.totalRepaidUnits), '</text>',
            // Footer
            '<rect x="22" y="222" width="376" height="1" fill="#1e3a5f"/>',
            '<text x="22" y="245" font-family="monospace" font-size="9" fill="#334155">POLYGON MAINNET  |  bankit.app  |  NON-TRANSFERABLE</text>',
            '</svg>'
        ));
    }

    function _scaleBar(uint8 score) internal pure returns (string memory) {
        // Maps 0-100 to 0-376px
        uint256 width = (uint256(score) * 376) / 100;
        return width.toString();
    }

    function _formatUnits(uint96 units) internal pure returns (string memory) {
        // BKD has 6 decimals. Show whole units only (divide by 10^6).
        uint256 whole = uint256(units) / 1_000_000;
        return whole.toString();
    }

    function supportsInterface(bytes4 interfaceId)
        public view override(ERC721, AccessControl) returns (bool)
    {
        return interfaceId == type(IERC5192).interfaceId
            || super.supportsInterface(interfaceId);
    }
}
