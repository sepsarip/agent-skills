#!/usr/bin/env python3
"""
parse_transcript.py — Normalizes .srt, .vtt, Whisper .json, or plain .txt meeting
transcripts into standardized [HH:MM:SS - HH:MM:SS] utterances, extracts the
canonical speaker roster, and generates a deterministic 30-day ISO 8601 Relative
Temporal Lookup Calendar anchored on --anchor-date.
Runs strictly on Python 3.8+ standard library.
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path


def normalize_hms(raw_ts: str) -> str:
    clean = raw_ts.strip().replace(",", ".").split(".")[0]
    parts = [int(p) for p in clean.split(":")]
    if len(parts) == 2:
        return f"00:{parts[0]:02d}:{parts[1]:02d}"
    if len(parts) == 3:
        return f"{parts[0]:02d}:{parts[1]:02d}:{parts[2]:02d}"
    return "00:00:00"


def hms_to_seconds(hms: str) -> int:
    parts = [int(p) for p in hms.split(":")]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def seconds_to_hms(sec: int) -> str:
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_relative_calendar(anchor_str: str) -> dict:
    try:
        anchor = datetime.date.fromisoformat(anchor_str)
    except ValueError:
        anchor = datetime.date.today()

    weekdays_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekdays_id = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

    cal = {
        "anchor_date_iso": anchor.isoformat(),
        "anchor_weekday_en": weekdays_en[anchor.weekday()],
        "anchor_weekday_id": weekdays_id[anchor.weekday()],
        "today": anchor.isoformat(),
        "tomorrow_besok": (anchor + datetime.timedelta(days=1)).isoformat(),
        "day_after_tomorrow_lusa": (anchor + datetime.timedelta(days=2)).isoformat(),
        "in_1_week": (anchor + datetime.timedelta(days=7)).isoformat(),
        "in_2_weeks": (anchor + datetime.timedelta(days=14)).isoformat(),
        "upcoming_30_days": [],
    }

    for offset in range(1, 31):
        d = anchor + datetime.timedelta(days=offset)
        w_en = weekdays_en[d.weekday()]
        w_id = weekdays_id[d.weekday()]
        week_label = "this_week" if d.isocalendar()[1] == anchor.isocalendar()[1] else (
            "next_week" if d.isocalendar()[1] == anchor.isocalendar()[1] + 1 else f"+{offset}d"
        )
        cal["upcoming_30_days"].append({
            "offset_days": f"+{offset}",
            "date_iso": d.isoformat(),
            "weekday_en": w_en,
            "weekday_id": w_id,
            "relative_bucket": week_label,
        })
    return cal


def parse_srt_or_vtt(content: str) -> list:
    utterances = []
    blocks = re.split(r"\n\s*\n", content.strip())
    ts_line_re = re.compile(
        r"(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\s*-->\s*(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)"
    )
    speaker_re = re.compile(r"^(?:<v\s+([^>]+)>|([A-Za-z0-9_ .\-]{2,30}):)\s*(.*)$")

    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip() and ln.strip() != "WEBVTT"]
        if not lines:
            continue
        ts_match = None
        text_lines = []
        for ln in lines:
            m = ts_line_re.search(ln)
            if m:
                ts_match = m
            elif ts_match:
                text_lines.append(ln)
        if ts_match and text_lines:
            start_hms = normalize_hms(ts_match.group(1))
            end_hms = normalize_hms(ts_match.group(2))
            joined = " ".join(text_lines)
            sp_m = speaker_re.match(joined)
            if sp_m:
                speaker = (sp_m.group(1) or sp_m.group(2)).strip()
                text = sp_m.group(3).strip()
            else:
                speaker = "Unknown_Speaker"
                text = joined
            utterances.append({
                "span": f"{start_hms} - {end_hms}",
                "start_sec": hms_to_seconds(start_hms),
                "end_sec": hms_to_seconds(end_hms),
                "speaker": speaker,
                "text": text,
            })
    return utterances


def parse_plain_txt(content: str) -> list:
    utterances = []
    # Matches patterns like: [00:14:22] Budi: Halo or 14:22 - 15:05 | Budi: Halo
    line_re = re.compile(
        r"^\[?(\d{1,2}:\d{2}(?::\d{2})?)(?:\s*[-–to]+\s*(\d{1,2}:\d{2}(?::\d{2})?))?\]?\s*[-|]?\s*(?:([A-Za-z0-9_ .\-]{2,30}):)?\s*(.+)$"
    )
    for ln in content.splitlines():
        stripped = ln.strip()
        if not stripped:
            continue
        m = line_re.match(stripped)
        if m:
            start_hms = normalize_hms(m.group(1))
            end_hms = normalize_hms(m.group(2)) if m.group(2) else seconds_to_hms(hms_to_seconds(start_hms) + 15)
            speaker = m.group(3).strip() if m.group(3) else "Unknown_Speaker"
            text = m.group(4).strip()
            utterances.append({
                "span": f"{start_hms} - {end_hms}",
                "start_sec": hms_to_seconds(start_hms),
                "end_sec": hms_to_seconds(end_hms),
                "speaker": speaker,
                "text": text,
            })
    return utterances


def parse_whisper_json(content: str) -> list:
    data = json.loads(content)
    segments = data.get("segments", data if isinstance(data, list) else [])
    utterances = []
    for seg in segments:
        s_sec = int(float(seg.get("start", 0)))
        e_sec = int(float(seg.get("end", s_sec + 10)))
        start_hms = seconds_to_hms(s_sec)
        end_hms = seconds_to_hms(e_sec)
        speaker = seg.get("speaker") or "Unknown_Speaker"
        text = str(seg.get("text", "")).strip()
        if text:
            utterances.append({
                "span": f"{start_hms} - {end_hms}",
                "start_sec": s_sec,
                "end_sec": e_sec,
                "speaker": speaker,
                "text": text,
            })
    return utterances


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize meeting transcript and generate anchor calendar.")
    parser.add_argument("transcript", help="Path to transcript (.srt, .vtt, .json, .txt)")
    parser.add_argument("--anchor-date", default=datetime.date.today().isoformat(), help="Meeting date YYYY-MM-DD")
    parser.add_argument("--output", default="-", help="Output JSON path ('-' for stdout)")
    args = parser.parse_args()

    t_path = Path(args.transcript)
    if not t_path.exists():
        print(f"Error: Transcript file '{t_path}' not found.", file=sys.stderr)
        return 1

    raw = t_path.read_text(encoding="utf-8", errors="replace")
    suffix = t_path.suffix.lower()

    if suffix == ".json":
        utterances = parse_whisper_json(raw)
    elif suffix in {".srt", ".vtt"} or "-->" in raw:
        utterances = parse_srt_or_vtt(raw)
    else:
        utterances = parse_plain_txt(raw)

    speakers = sorted({u["speaker"] for u in utterances if u["speaker"] != "Unknown_Speaker"})
    max_sec = max((u["end_sec"] for u in utterances), default=0)

    payload = {
        "source_file": str(t_path),
        "utterance_count": len(utterances),
        "max_timestamp": seconds_to_hms(max_sec),
        "max_seconds": max_sec,
        "speakers_detected": speakers,
        "relative_calendar": build_relative_calendar(args.anchor_date),
        "utterances": utterances,
    }

    out_json = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output == "-":
        print(out_json)
    else:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out_json, encoding="utf-8")
        print(f"✅ Parsed {len(utterances)} utterances (max {payload['max_timestamp']}) -> {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

