# Strict Scope Boundary: URS vs. SRS (ISO/IEC/IEEE 29148)

A User Requirement Specification (URS) document **ONLY** describes the **Problem Domain** (what users need to accomplish and observe externally). The agent is **STRICTLY PROHIBITED** from inserting **Solution Domain** implementation details (how the system is constructed internally).

| Dimension | ✅ REQUIRED in URS (Problem Domain) | ❌ FORBIDDEN in URS — Belongs to SRS/FDS (Solution Domain) |
| :--- | :--- | :--- |
| **Perspective** | Operational actor needs & end-to-end business workflows. | Internal architecture, codebase layout, technology stack choices. |
| **Functional Statement** | System behaviors directly observable by the user (*observable behavior*). | Internal algorithms, cron jobs, background message queues, memory management. |
| **Data Structure** | Conceptual business entities (e.g., "Customer Profile", "Sales Invoice"). | Database table schemas, SQL column names, database data types (`VARCHAR`, `INT`, `UUID`), Primary/Foreign Keys. |
| **Interfaces & Communication** | Business-level user interactions (e.g., "Finance Manager uploads payment proof document"). | API Endpoint specifications (`POST /api/v1/upload`), JSON/XML payloads, HTTP status codes (`200`, `404`), SSL/TLS ciphers. |
| **Actor Identity** | Operational human roles or external organizations (e.g., `Finance Manager`, `Registered Buyer`). | Internal system components or development team roles (e.g., `Database Controller`, `Microservice`, `Developer`, `System`). |

## Prohibited Terms Blacklist in URS (SRS Leakage)
If any of these terms appear within requirement specifications, `validate_urs.py` will fail the document:
- **Database:** `SQL`, `PostgreSQL`, `MySQL`, `MongoDB`, `Redis`, `VARCHAR`, `BOOLEAN`, `INT`, `Primary Key`, `Foreign Key`, `DB Table`, `Query`.
- **Backend/API:** `REST API`, `GraphQL`, `gRPC`, `JSON payload`, `Endpoint`, `Microservice`, `Cron job`, `Webhook`, `Docker`, `Kubernetes`, `Kafka`.
- **Frontend/Code:** `React`, `Vue`, `Flutter`, `CSS`, `DOM`, `State management`, `Redux`, `Controller`, `Repository pattern`.
