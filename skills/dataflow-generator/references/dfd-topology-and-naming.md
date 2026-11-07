# Yourdon/DeMarco & Gane/Sarson DFD Topology & Naming Standards

## 1. Deterministic Translation Rules (URS to DFD)
| DFD Element | Prefix | Extraction Rule from URS | Abstraction & Grouping Strategy |
| :--- | :--- | :--- | :--- |
| **External Entity ($EE$)** | `ACT-XX` | Extracted from `"As a [Role]"` or external third-party systems in Acceptance Criteria. | Consolidate synonymous human roles (e.g., Buyer & Customer $\to$ `ACT-01: Customer`). |
| **Process ($P$)** | `P0`, `P1.0`, `P1.1` | Extracted from `"I want to [Action + Object]"` and Acceptance Criteria workflows. | Aggregate closely related actions under their parent `EPIC-XX` to prevent graph clutter. |
| **Data Store ($DS$)** | `DS-XX` | Extracted from persistent business nouns read or written in Acceptance Criteria. | Consolidate identical entity states into a single canonical repository (e.g., `DS-01: Order Repository`). |
| **Data Flow ($DF$)** | `DF-XX` | Extracted from user triggers/inputs and observable system outputs/responses. | Each flow represents a discrete information packet moving in a **single direction**. |

---

## 2. Syntactic Naming & Hierarchical Numbering Rules

### A. Naming Grammar
1. **Process ($P$):** MUST be **`Active Verb + Object Noun Phrase`**.
   - ✅ **VALID:** `Verify User Credentials`, `Process Order Payment`, `Generate Monthly Tax Report`
   - ❌ **INVALID:** `User Login` (Actor + Noun), `Data Processing` (Vague passive noun), `Database Storage` (Noun)
2. **Data Flow ($DF$) & Data Store ($DS$):** MUST be **`Noun / Noun Phrase`** (Zero verbs, zero control flags).
   - ✅ **VALID:** `Login Credentials`, `Payment Invoice`, `DS-01: Customer Profile Records`
   - ❌ **INVALID:** `Send OTP to User` (Contains verb), `Process Payment` (Process name), `True/False Flag` (Control signal, not data)

### B. Hierarchical Numbering
- **Context Diagram (Level 0):** Single process numbered `P0: <System Name>`.
- **DFD Level 1:** Major functional processes numbered `P1.0`, `P2.0`, `P3.0` (maximum $7 \pm 2$, i.e., 5 to 9 processes per diagram).
- **DFD Level 2 (if decomposed):** Hierarchical dot notation `P1.1`, `P1.2`, `P1.3`.

---

## 3. Permissible Graph Connectivity Matrix
Model the DFD as a directed multi-graph $G = (V, E)$ where $V = EE \cup P \cup DS$. Every directed edge $e = (u, v) \in E$ MUST obey:

| Source Node ($u$) | Target: External Entity ($EE$) | Target: Process ($P$) | Target: Data Store ($DS$) |
| :--- | :--- | :--- | :--- |
| **External Entity ($EE$)** | ❌ **ILLEGAL** (System Boundary Bypass) | ✅ **VALID** (External Input) | ❌ **ILLEGAL** (Direct Storage Access) |
| **Process ($P$)** | ✅ **VALID** (External Output) | ✅ **VALID** (Inter-Process Flow) | ✅ **VALID** (Data Write / Update) |
| **Data Store ($DS$)** | ❌ **ILLEGAL** (Direct Exposure Violation) | ✅ **VALID** (Data Read / Fetch) | ❌ **ILLEGAL** (Direct Store Sync) |

---

## 4. Mathematical Definitions of Topological Anomalies
1. **Black Hole Anomaly:** A process absorbs data but emits zero outputs.
   $$\text{deg}^-(p) \ge 1 \quad \land \quad \text{deg}^+(p) = 0$$
2. **Miracle (Spontaneous Generation) Anomaly:** A process emits output data without receiving any input trigger or data fetch.
   $$\text{deg}^-(p) = 0 \quad \land \quad \text{deg}^+(p) \ge 1$$
3. **Grey Hole Anomaly:** Input attributes entering process $p$ are logically insufficient to compute the emitted output attributes:
   $$\bigcup_{e_{in} \in I(p)} \text{Attributes}(e_{in}) \not\supseteq \text{RequiredAttributes}\left(\bigcup_{e_{out} \in O(p)} \text{Attributes}(e_{out})\right)$$
4. **Parent-Child Balancing Violation:** The set of net external flows entering and leaving $P_0$ in Level 0 must equal the set of external flows entering and leaving all Level 1 processes $P_{L1}$:
   $$\bigcup_{p \in P_{L1}} I_{ext}(p) = I(P_0) \quad \land \quad \bigcup_{p \in P_{L1}} O_{ext}(p) = O(P_0)$$
5. **Bi-directional / Unlabeled Edge Violation:** Every arrow must be unidirectional (`-->`) and explicitly labeled with its payload name. Double-headed arrows (`<-->`) are strictly forbidden.

