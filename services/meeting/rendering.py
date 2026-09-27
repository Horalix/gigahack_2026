"""Deterministic, self-contained HTML minutes renderer."""

from html import escape


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def render_minutes_html(meeting: dict, segments: list[dict], decisions: dict,
                       *, reviewer: str, approved_at: str) -> bytes:
    """Render only an explicitly approved snapshot; escape every source string."""
    actions = []
    for item in decisions.get("items", []):
        if item.get("reviewStatus", "accepted") != "accepted":
            continue
        quotes = "".join(
            f'<blockquote><time>{_e(round(e.get("startMs", 0) / 1000))}s</time> “{_e(e.get("quote", ""))}”</blockquote>'
            for e in item.get("taskEvidence", [])
        ) or '<p class="muted">No supporting excerpt was supplied.</p>'
        actions.append(
            f'<article class="action"><p class="meta">{_e(item.get("kind", "item"))} · {_e(item.get("status", "unresolved"))}</p>'
            f'<h3>{_e(item.get("text", ""))}</h3><p><b>Owner:</b> {_e(item.get("ownerLabel") or "Unassigned")} '
            f'&nbsp; <b>Due:</b> {_e(item.get("originalDateExpression") or "No deadline stated")}</p>{quotes}</article>'
        )
    if not actions:
        actions.append('<p class="muted">No decisions or follow-up actions were identified.</p>')
    transcript = "".join(
        f'<p class="line"><time>{_e(round(segment.get("start_ms", segment.get("startMs", 0)) / 1000))}s</time>'
        f'<span lang="{_e(segment.get("language", "und"))}">{_e(segment.get("text", ""))}</span></p>'
        for segment in segments
    ) or '<p class="muted">No transcript passages are available.</p>'
    title = meeting.get("title", "Meeting minutes")
    revision = meeting.get("transcript_revision", meeting.get("transcriptRevision", ""))
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title><style>
@page{{size:A4;margin:18mm}}body{{font:15px/1.55 Arial,sans-serif;color:#17212b;max-width:850px;margin:32px auto;padding:0 24px}}
h1,h2,h3{{line-height:1.2}}h1{{margin-bottom:4px}}.meta,.muted{{color:#647582;font-size:13px}}.notice{{border:1px solid #4c8178;background:#edf7f4;padding:12px;border-radius:6px}}
.action{{border-top:1px solid #dce4e8;padding:12px 0}}blockquote{{border-left:3px solid #77a79f;margin:8px 0;padding:4px 12px;color:#354b55}}blockquote time{{font-size:12px;color:#687985;margin-right:8px}}
.line{{display:grid;grid-template-columns:60px 1fr;gap:12px;border-bottom:1px solid #edf0f2;padding:7px 0;margin:0}}.line time{{font-size:12px;color:#71808b}}footer{{border-top:1px solid #dce4e8;margin-top:28px;padding-top:12px;color:#647582;font-size:12px}}
</style></head><body>
<h1>{_e(title)}</h1><p class="meta">{_e(meeting.get('recorded_at', meeting.get('recordedAt', '')))} · {_e(meeting.get('time_zone', meeting.get('timeZone', '')))} · language {_e(meeting.get('output_language', meeting.get('outputLanguage', '')))}</p>
<div class="notice"><b>Clinician reviewed</b> · {_e(reviewer)} · {_e(approved_at)}<br>Meeting ID {_e(meeting.get('id', ''))} · Transcript revision {_e(revision)}</div>
<h2>Decisions and actions</h2>{''.join(actions)}<h2>Transcript</h2>{transcript}
<footer>Generated locally by Notavra. This file reflects transcript revision {_e(revision)}. Review the source recording when a clinical detail is uncertain.</footer>
</body></html>"""
    return document.encode("utf-8")
