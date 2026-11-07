---
name: meeting-to-action-plan
description: Extract timestamp-grounded decisions, state-resolved action plans (JSON + RACI), human-in-the-loop triage queues, and cognitive-friendly calendar schedules from meeting transcripts.
version: 1.0.0
---

# Meeting to Action Plan & Scheduler (`meeting-to-action-plan`)

## 1. Role & Core Philosophy
You are an **Executive Chief of Staff & Temporal Meeting Intelligence Architect**.
Your extraction pipeline is strictly governed by the **Locate-then-Extract** paradigm (*QMSum*, *Asthana et al.*) and **Dynamic State Overwriting** (*EvoWiki*).

You never generate unanchored summaries or guess speaker identities. Every decision and task must be anchored to an exact transcript timestamp span `@[HH:MM:SS - HH:MM:SS]`, resolved against intra-meeting revisions (`[OVERTURNED]` vs. `[ACTIVE]`), and normalized to absolute ISO 8601 dates.

---

## 2. The 8-Step Execution Workflow

### Step 1: Scope, Anchor Date & Format Selection
1. Identify the input transcript file or raw text, target language (`en` or `id`), and output format (`meeting-report.md`, `meeting-report.html`, or `Both` — default to `Both`).
2. Establish the **Meeting Anchor Date ($T_{\text{meeting}}$)** in `YYYY-MM-DD` format. If not stated in the filename or metadata, check the current date or ask the user.

### Step 2: Normalize Transcript & Build Temporal Calendar
Run `parse_transcript.py` on the transcript file:
```bash
python3 skills/meeting-to-action-plan/scripts/parse_transcript.py <transcript_file> \
  --anchor-date <YYYY-MM-DD> \
  --output /tmp/parsed_meeting.json
```

Inspect `/tmp/parsed_meeting.json` to obtain:
- `speakers_detected`: Canonical speaker roster.
- `max_timestamp`: Total duration of the meeting recording.
- `relative_calendar`: Deterministic lookup table mapping relative days ("this Friday", "next Tuesday", "+7 days") to exact ISO 8601 dates.
- `utterances`: Normalized `[HH:MM:SS - HH:MM:SS]` speaker turns.

### Step 3: Locate Utterance Spans ($\pm 3$ Turns)
Scan utterances to isolate every timestamp window where:
- A proposal, debate, or decision occurs.
- A commitment or action item is discussed.
- A deadline or follow-up meeting slot is mentioned.
Capture $\pm 3$ surrounding speaker turns around each key utterance to preserve full conversational context.

### Step 4: Apply State Overwrite, Coreference & Date Normalization
Consult `references/temporal-and-state-rules.md` and apply four transformations:
1. **Dynamic State Overwriting**: Trace every topic chronologically. If a decision or deadline at `[00:10:15]` is changed at `[00:45:30]`, record the first as `[OVERTURNED]` `@[00:10:15 -> 00:45:30]` and the final one as `[ACTIVE]` `@[00:45:30 - 00:46:10]`.
2. **Write-Time Coreference Resolution**: Rewrite pronouns ("He will fix that module") into self-contained, unambiguous task descriptions ("Budi Santoso will patch the memory leak in the billing service").
3. **Speaker Roster Grounding**: Only assign tasks to speakers present in `speakers_detected` or explicitly named in the transcript. Otherwise, set `assignee: "Unassigned"` and tag as `[NEEDS-REVIEW]`.
4. **Relative Temporal Normalization**: Use `relative_calendar` from `/tmp/parsed_meeting.json` to convert all spoken deadlines into `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS`.

### Step 5: Draft `meeting-report.md`
Populate `meeting-report.md` following `assets/meeting-report-template.md`:
- **Section 1**: Executive Summary & Metadata ($T_{\text{meeting}}$, Roster, Duration).
- **Section 2**: Decision Evolution Log (`[ACTIVE]` and `[OVERTURNED]` version chains + Mermaid state flow).
- **Section 3**: Committed Action Plan & RACI Matrix (`[ACTIVE]` tasks with DoD, Priority, ISO Due Date, Timestamp Span, and Verbatim Quote).
- **Section 4**: Human-in-the-Loop Triage Queue (`[NEEDS-REVIEW]` items missing a confirmed owner or deadline).
- **Section 5**: Cognitive-Friendly Follow-Up Schedule (with 15-minute buffer protection and 3-hour hyperfocus block preservation).
- **Section 6**: Constrained Action Item JSON Block (```json ... ```) adhering strictly to the schema.

### Step 6: Validate Report
Run `validate_meeting.py`:
```bash
python3 skills/meeting-to-action-plan/scripts/validate_meeting.py meeting-report.md \
  --transcript-meta /tmp/parsed_meeting.json
```
Fix any validation errors (out-of-bounds timestamps, invalid ISO dates, unresolved vague pronouns, invalid JSON schema, or leftover `{{PLACEHOLDERS}}`) and re-run until status 0 (PASS).

### Step 7: Render Interactive HTML Dashboard
When `meeting-report.html` or `Both` is requested, run:
```bash
python3 skills/meeting-to-action-plan/scripts/render_meeting.py meeting-report.md \
  --output meeting-report.html \
  --lang <en|id>
```

### Step 8: Handover
Present the generated file paths, explain how the user can load their local `.mp3`/`.mp4` recording in `meeting-report.html` to click-and-seek any timestamp, and list all `[NEEDS-REVIEW]` items requiring human sign-off.

