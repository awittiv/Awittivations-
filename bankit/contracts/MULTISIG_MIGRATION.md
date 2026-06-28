# Bankit Governance → Multisig Migration Runbook

Moves **governance/admin** control of the 6 live Polygon-mainnet contracts off the
single hot oracle key (`0x2130a45146b22FA480a0e573a5aDBA45259dEe0e`, plaintext in
`backend/.env`) and onto a Gnosis Safe. The **operational** `ORACLE_ROLE` /
`ATTESTER_ROLE` stay on the current key, so the backend keeps disbursing.

## What moves vs. what stays

| Contract | Address | → Safe (governance) | Stays on hot key (ops) |
|---|---|---|---|
| BankitStablecoin | `0x920DBEFF9900cE3B37f76754C05fa15c6575822E` | `DEFAULT_ADMIN_ROLE`, `COMPLIANCE_ROLE` (pause) | — |
| BankitLiquidityRouter | `0x5fc2180fAA7ac70c6a6F22796253Be89F45022Cf` | `DEFAULT_ADMIN_ROLE` | `ORACLE_ROLE` |
| BankitCreditPassport | `0x8010dFF392691371999F1B6C88001EB998a01129` | `DEFAULT_ADMIN_ROLE` | `ORACLE_ROLE` |
| ComplianceAttestation | `0x8BdA80df379555EEd9A1a45dc959C41f9e01335c` | `DEFAULT_ADMIN_ROLE` | `ATTESTER_ROLE` |
| AtomicDisbursement | `0xc3d3150A7d0a5fD1aC85f048fe283d2F82083396` | `Ownable` owner | — |
| RailsVault | `0xb66aebf16Dc6A77B0cfC49d10A4295d388ecf4Ff` | — (signature-based, no admin) | — |

## Step 0 — Create the Safe (recommended: 2-of-3)

A 2-of-3 Safe means any 2 of 3 keys must approve. No single key loss locks you
out, and no single key compromise gives an attacker control.

Suggested signers:
1. **Primary** — hardware wallet (Ledger/Trezor), your day-to-day signer.
2. **Backup** — a second device / different seed, stored separately.
3. **Cold backup** — offline key (paper/steel) or a trusted co-signer, used only
   in recovery.

Create it:
1. Go to https://app.safe.global → connect your primary wallet → **Create new Safe**.
2. Network: **Polygon**.
3. Add the 3 signer addresses, set threshold to **2**.
4. Deploy (costs a little POL for gas). Copy the resulting Safe address — this is `MULTISIG`.

> Do NOT make any signer the current oracle key `0x2130…dEe0e`. The whole point is
> to remove that key from the trust root.

## Step 1 — Phase 1: GRANT (reversible)

From `bankit/contracts`, with `backend/.env` values exported (or load them in shell):

```bash
export ORACLE_PRIVATE_KEY=<current admin key from backend/.env>
export MULTISIG=0xYourSafeAddress
export STABLECOIN_ADDRESS=0x920DBEFF9900cE3B37f76754C05fa15c6575822E
export CONTRACT_ADDRESS=0x5fc2180fAA7ac70c6a6F22796253Be89F45022Cf
export PASSPORT_ADDRESS=0x8010dFF392691371999F1B6C88001EB998a01129
export COMPLIANCE_ATTESTATION_ADDRESS=0x8BdA80df379555EEd9A1a45dc959C41f9e01335c
export ATOMIC_DISBURSEMENT_ADDRESS=0xc3d3150A7d0a5fD1aC85f048fe283d2F82083396

forge script script/TransferToMultisig.s.sol:TransferToMultisig \
  --rpc-url polygon --broadcast -vvvv
```

This grants admin/compliance roles to the Safe. The old key **keeps** admin too,
so this phase is fully reversible.

## Step 2 — Prove the Safe controls the contracts

Before dropping the old key, do a real action from the Safe. Easiest test:
in the Safe web UI → **New transaction → Contract interaction**:
- Target `STABLECOIN_ADDRESS`, call `pause()`, collect 2 signatures, execute.
- Confirm it paused (any transfer/mint now reverts), then call `unpause()` the same way.

Verify role state with `cast` (replace `$SAFE`):

```bash
# DEFAULT_ADMIN_ROLE is 0x0000...0000
cast call $STABLECOIN_ADDRESS "hasRole(bytes32,address)(bool)" \
  0x0000000000000000000000000000000000000000000000000000000000000000 $SAFE --rpc-url polygon
```

## Step 3 — Phase 2: FINALIZE (irreversible)

Only after the Safe test passes. This transfers `AtomicDisbursement` ownership to
the Safe and **renounces** the old key's governance roles (the script asserts the
Safe already holds everything before renouncing).

```bash
FINALIZE=true forge script script/TransferToMultisig.s.sol:TransferToMultisig \
  --rpc-url polygon --broadcast -vvvv
```

After this: the old key can still call `releaseMicroLiquidity` / `repayLoan` /
passport updates / `attest` (operational), but can no longer grant roles, pause,
or change ownership. Governance lives in the Safe.

## Step 4 — Reduce the remaining hot-key risk

The ops key is still derived from `WALLET_MASTER_SEED` sitting plaintext in
`backend/.env`. Follow-ups (separate task):
- Move the seed/ops key into a secret manager (Fly secrets / AWS Secrets Manager),
  not the host `.env`.
- Consider rotating the ops `ORACLE_ROLE`/`ATTESTER_ROLE` to a fresh dedicated key
  (the Safe can `grantOracleRole`/`grantRole` to the new key and revoke the old one).
- Cap exposure: keep only minimal POL for gas on the ops key; the treasury should
  not share the ops key.

## Rollback

- **Before Phase 2:** old key still has admin — just `revokeRole` the Safe if needed.
- **After Phase 2:** irreversible from the old key. Recovery requires the Safe
  (2-of-3) to re-grant roles. This is why Step 2 is mandatory.
