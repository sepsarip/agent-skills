# Meeting to Action Plan & Scheduler Skill

Convert raw meeting transcripts (`.srt`, `.vtt`, Whisper `.json`, Zoom/Teams/Meet `.txt`) into timestamp-grounded decision logs, state-aware action plans, RACI matrices, and calendar-ready schedules.

## 📌 Overview

Standard AI meeting summarizers suffer from three critical failure modes:
1. **Unanchored Claims & Speaker Hallucinations**: Action items are listed without exact audio timestamps (`[HH:MM:SS - HH:MM:SS]`) or verbatim quotes, forcing teams to re-listen to hour-long recordings when disputes arise.
2. **Stale Decision Retrieval**: Early proposals at minute 10 that get overturned at minute 45 are mistakenly recorded as final decisions.
3. **Unresolved Relative Dates**: Spoken deadlines like *"next Friday"* or *"in two weeks"* remain vague text instead of normalized ISO 8601 calendar dates (`YYYY-MM-DD`).

The `meeting-to-action-plan` skill solves this using a **Locate-then-Extract** architecture grounded in empirical meeting intelligence research (*QMSum*, *Asthana et al.*, *EvoWiki*). Every decision and task carries a lifecycle provenance tag (`[ACTIVE]`, `[OVERTURNED]`, or `[NEEDS-REVIEW]`) anchored to exact audio timestamps.

## 🚀 Key Features

* **Click-to-Seek Audio Timestamp Grounding**: Every decision and task is cited as `[HH:MM:SS - HH:MM:SS]`. In the HTML dashboard, loading a local audio/video file lets users click any timestamp badge to immediately jump and play that exact second of the recording.
* **Dynamic State Overwriting (EvoWiki Protocol)**: Tracks intra-meeting micro-evolution (`Proposal ➡️ Debate ➡️ Final Resolution`), marking superseded proposals as `[OVERTURNED]` while keeping final decisions `[ACTIVE]`.
* **Deterministic Temporal Normalization**: `parse_transcript.py` generates a 30-day calendar lookup table anchored to the meeting date ($T_{\text{meeting}}$), converting relative phrases (*"next Friday"*) into strict ISO 8601 dates.
* **Human-in-the-Loop Triage Queue**: Ambiguous tasks (`Unassigned` owner, missing deadline, or low confidence) are automatically isolated into a `[NEEDS-REVIEW]` triage table.
* **Cognitive-Friendly Auto-Scheduler**: Generates downloadable `.ics` calendar invites with built-in **15-minute cognitive buffers** and **hyperfocus block protection**.
* **Standard Library Tooling**: All bundled scripts run on Python 3.8+ standard library—zero `pip install` required.

## 📂 Skill Architecture

```text
skills/meeting-to-action-plan/
├── SKILL.md                              # Agent instructions, trigger definitions & rules
├── README.md                             # Human-readable documentation & script guide
├── assets/
│   ├── meeting-report-template.md        # Structural Markdown & JSON schema template
│   └── meeting-report-template.html      # Interactive HTML shell with audio seek & .ics export
├── references/
│   └── temporal-and-state-rules.md       # Locate-then-Extract, State Overwrite & Coreference guide
└── scripts/
    ├── parse_transcript.py               # Transcript normalizer & Anchor Calendar generator
    ├── validate_meeting.py               # Timestamp bounds, JSON schema & coreference validator
    └── render_meeting.py                 # Markdown-to-interactive HTML compiler
```

## 🔄 The 8-Step Workflow

When an agent activates this skill, it executes the following structured workflow:

1. **Scope, Anchor Date & Format Selection**: Establish transcript source, meeting anchor timestamp ($T_{\text{meeting}}$, e.g. `2026-11-04`), language (`en` or `id`), and output format (`meeting-report.md`, `meeting-report.html`, or `Both`).
2. **Normalize Transcript & Build Calendar**: Execute `parse_transcript.py` to normalize utterances into `[HH:MM:SS - HH:MM:SS]`, extract the speaker roster, and generate the deterministic 30-day ISO 8601 lookup calendar.
3. **Locate Utterance Spans**: Scan normalized utterances to locate candidate windows ($\pm 3$ surrounding turns) where decisions, debates, tasks, or follow-up schedules occur.
4. **Resolve State Evolution & Temporal Dates**: Consult `references/temporal-and-state-rules.md` to separate `[OVERTURNED]` proposals from `[ACTIVE]` resolutions, apply coreference resolution, and map relative dates to ISO 8601.
5. **Write Meeting Report**: Populate `meeting-report.md` based on `assets/meeting-report-template.md`, including the Executive Summary, Decision Evolution Log, RACI Action Plan, Triage Queue, Follow-Up Schedule, and Constrained JSON block.
6. **Validate Report**: Run `validate_meeting.py` to verify timestamp citations against recording duration, validate the JSON schema, check ISO 8601 dates, and reject vague pronouns in task descriptions.
7. **Render Interactive Dashboard**: When HTML or Both is requested, run `render_meeting.py` to compile `meeting-report.md` into `meeting-report.html` with click-to-seek audio playback and `.ics` calendar export.
8. **Handover**: Present output file path(s) and highlight `[NEEDS-REVIEW]` triage items requiring manager/team confirmation.

## 🏷️ Lifecycle & Provenance Rules

Every extracted decision, deadline change, and action item must carry one of three explicit state tags:

| Tag | Definition | Required Evidence |
| :--- | :--- | :--- |
| `[ACTIVE]` | Final, currently valid decision or committed action item. | Timestamp span `@[HH:MM:SS - HH:MM:SS]`, verified speaker, and verbatim quote. |
| `[OVERTURNED]` | Earlier proposal, deadline, or scope that was rejected or superseded later in the meeting. | Initial span `@[HH:MM:SS]` plus overriding span `-> @[HH:MM:SS]` and rationale. |
| `[NEEDS-REVIEW]` | Task with missing assignee (`Unassigned`), missing deadline (`TBD`), or implicit commitment (`confidence < 0.80`). | Timestamp span `@[HH:MM:SS - HH:MM:SS]` and explicit clarification question. |

## 🛠️ Bundled Scripts

All scripts are located in `scripts/` and run using Python 3.8+ standard library:

### 1. `parse_transcript.py`
Parses `.srt`, `.vtt`, Whisper `.json`, or plain `.txt` transcripts into normalized `[HH:MM:SS - HH:MM:SS]` segments and computes a 30-day relative calendar table anchored on `--anchor-date`.

```bash
python3 skills/meeting-to-action-plan/scripts/parse_transcript.py transcript.vtt \
  --anchor-date 2026-11-04 \
  --output /tmp/parsed_meeting.json
```

### 2. `validate_meeting.py`
Validates timestamp bounds, ISO 8601 dates, coreference clarity, and the embedded Action Item JSON schema.

```bash
python3 skills/meeting-to-action-plan/scripts/validate_meeting.py meeting-report.md \
  --transcript-meta /tmp/parsed_meeting.json
```

### 3. `render_meeting.py`
Compiles `meeting-report.md` into a self-contained interactive `meeting-report.html` dashboard with local audio click-to-seek, Mermaid flowcharts, and one-click `.ics` calendar generation.

```bash
python3 skills/meeting-to-action-plan/scripts/render_meeting.py meeting-report.md \
  --output meeting-report.html \
  --lang id
```

