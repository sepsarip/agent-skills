# xDECAF Semantic Security & STRIDE Threat Modeling Rules

## 1. Trust Boundaries (`TB-XX`)
A Trust Boundary (`TB-01`, `TB-02`, ...) MUST be drawn around nodes sharing the same privilege level or network perimeter:
- **`TB-01: Untrusted Public Zone`** — External human actors (`ACT-XX`) and third-party webhooks.
- **`TB-02: Application DMZ / Service Boundary`** — Core functional processes (`P1.0 ... Pn.0`).
- **`TB-03: Restricted Persistence Zone`** — Internal Data Stores (`DS-XX`) containing sensitive records.

## 2. Data Sensitivity Classification Labels
Every Data Flow (`DF-XX`) and Data Store (`DS-XX`) must carry at least one sensitivity label:
- `$Public` — Non-sensitive public information.
- `$Internal` — Operational business data.
- `$Confidential` — Financial, proprietary, or commercial trade data.
- `$PII` — Personally Identifiable Information (subject to GDPR/privacy laws).
- `$Credentials` — Passwords, tokens, cryptographic keys, session secrets.

## 3. xDECAF Policy Constraints (`neverFlows`)
Enforce semantic security invariants across the graph:
1. `Data with ($PII or $Credentials) neverFlows StorageNode with $Unencrypted`
2. `Data with $Credentials neverFlows ExternalEntity (unless explicitly hashed/tokenized as session token)`

## 4. STRIDE Threat Matrix Across Trust Boundaries
For every Data Flow crossing a Trust Boundary (`TB-XX`), evaluate and document mitigations for:

| STRIDE Category | Vulnerable DFD Target | Security Failure Mechanism | Required Mitigation Control |
| :--- | :--- | :--- | :--- |
| **S — Spoofing** | $EE \to P$ crossing TB | Forged actor identity at system entry point. | OAuth2/OIDC, mTLS, or signed API token verification. |
| **T — Tampering** | $DF$ crossing TB | Man-in-the-middle modification of payload in transit. | TLS 1.3 in transit, HMAC payload signature verification. |
| **R — Repudiation** | Process ($P$) | State-changing action executed without immutable audit trail. | Append-only audit log write to dedicated Data Store. |
| **I — Info Disclosure** | $DS$ or $DF$ crossing TB | Plaintext sniffing or unauthorized storage read of `$PII`/`$Confidential`. | AES-256 encryption at rest (`DS-XX`) and TLS 1.3 in transit. |
| **D — Denial of Service** | Entry Process ($P$) | Request flooding exhausting process compute capacity. | Rate limiting, throttling, and payload size quotas. |
| **E — Elevation of Privilege** | Process ($P$) | Malformed input payload triggering unauthorized role execution. | Strict schema validation and RBAC permission check inside Process. |

> **Anti-Hallucination Rule:** If encryption standards or auth protocols are not explicitly stated in the source URS, recommend standard controls above and tag them with `[ASSUMPTION]`.

