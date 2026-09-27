"""Send PDF(s) from pdf_to_send/ to the local Mailpit sink as email attachments.

A standalone test of the delivery hop: proves the mail path can carry a real
minutes document, not just a text body. Standard library only, so it runs under
the same offline constraints as the pipeline.

    python scripts/send_pdf.py
    python scripts/send_pdf.py --file sample-minutes.pdf --to cmo@medpark.local
    python scripts/send_pdf.py --no-verify

Every PDF in the folder is attached to one message by default, which mirrors
"minutes plus annex". Use --file to send just one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import smtplib
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FOLDER = REPO_ROOT / "pdf_to_send"

# The Windows console is cp1252; printing Romanian or Cyrillic raises
# UnicodeEncodeError and looks like a mail bug when it is only a display bug.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def find_pdfs(folder: Path, only: str | None) -> list[Path]:
    if not folder.is_dir():
        die(f"Folder not found: {folder}")

    if only:
        candidate = folder / only
        if not candidate.is_file():
            die(f"No such file: {candidate}")
        found = [candidate]
    else:
        found = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".pdf" and p.is_file())

    if not found:
        die(f"No PDF files in {folder}. Drop one in and run again.")

    # A file named .pdf is not necessarily a PDF. Catching a renamed .docx here
    # beats having a recipient open an unreadable attachment.
    for p in found:
        with p.open("rb") as fh:
            magic = fh.read(5)
        if magic != b"%PDF-":
            die(f"{p.name} does not start with %PDF- (got {magic!r}); not a real PDF")
    return found


def build_message(pdfs: list[Path], sender: str, recipients: list[str], subject: str) -> EmailMessage:
    msg = EmailMessage()

    # Message-ID derived from the attachment bytes, so re-sending the same
    # document after an ambiguous SMTP timeout is idempotent rather than
    # filing a duplicate. The real delivery stage should hash the MoM snapshot.
    digest = hashlib.sha256()
    for p in sorted(pdfs):
        digest.update(p.name.encode("utf-8"))
        digest.update(p.read_bytes())
    content_hash = digest.hexdigest()

    msg["Message-ID"] = make_msgid(idstring=content_hash[:16], domain="medpark.local")
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["X-Mom-Attachment-Hash"] = content_hash

    listing = "\n".join(f"  - {p.name} ({p.stat().st_size:,} bytes)" for p in pdfs)
    msg.set_content(
        "Proces-verbal atașat / Minutes attached.\n\n"
        f"{len(pdfs)} document(s):\n{listing}\n\n"
        "-- \n"
        "Sent by scripts/send_pdf.py to the local Mailpit sink.\n"
        "Delivered entirely within this machine over loopback SMTP.\n",
        charset="utf-8",
    )

    for p in pdfs:
        ctype, _ = mimetypes.guess_type(p.name)
        maintype, _, subtype = (ctype or "application/pdf").partition("/")
        msg.add_attachment(
            p.read_bytes(),
            maintype=maintype,
            subtype=subtype or "pdf",
            filename=p.name,
        )
    return msg


def api(base: str, path: str) -> dict | None:
    with urllib.request.urlopen(f"{base}{path}", timeout=5) as resp:
        body = resp.read()
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def verify(web_base: str, msgid: str, expected: list[Path]) -> int:
    deadline = time.monotonic() + 10
    found = None
    while time.monotonic() < deadline and not found:
        listing = api(web_base, "/api/v1/messages?limit=50") or {}
        for m in listing.get("messages", []):
            if m.get("MessageID") == msgid.strip("<>"):
                found = m
                break
        if not found:
            time.sleep(0.25)

    if not found:
        print(f"[4/4] verify   message {msgid} never arrived", file=sys.stderr)
        return 1

    full = api(web_base, f"/api/v1/message/{found['ID']}") or {}
    attachments = full.get("Attachments") or []
    by_name = {a.get("FileName"): a for a in attachments}

    problems = []
    for p in expected:
        got = by_name.get(p.name)
        if not got:
            problems.append(f"{p.name}: missing from the delivered message")
            continue
        if got.get("ContentType") != "application/pdf":
            problems.append(f"{p.name}: content type is {got.get('ContentType')!r}, expected application/pdf")
        # Mailpit reports the decoded size; a mismatch means the bytes changed
        # in transit, which a base64 or line-ending bug would cause.
        if got.get("Size") not in (None, p.stat().st_size):
            problems.append(f"{p.name}: size {got.get('Size')} != {p.stat().st_size} on disk")

    if problems:
        print("[4/4] verify   FAILED", file=sys.stderr)
        for prob in problems:
            print(f"               - {prob}", file=sys.stderr)
        return 1

    names = ", ".join(a.get("FileName", "?") for a in attachments)
    print(f"[4/4] verify   OK  {len(attachments)} attachment(s) intact: {names}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", type=Path, default=DEFAULT_FOLDER, help="source folder (default: pdf_to_send/)")
    ap.add_argument("--file", help="send only this filename from the folder")
    ap.add_argument("--from", dest="sender", default="minutes@medpark.local")
    ap.add_argument("--to", action="append", help="recipient; repeatable (default: ceo@medpark.local)")
    ap.add_argument("--subject", default="Proces-verbal — minutes attached (тест)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1025)
    ap.add_argument("--web-port", type=int, default=8025)
    ap.add_argument("--no-verify", action="store_true", help="skip reading the message back")
    args = ap.parse_args()

    recipients = args.to or ["ceo@medpark.local"]
    web_base = f"http://127.0.0.1:{args.web_port}"

    pdfs = find_pdfs(args.folder, args.file)
    total = sum(p.stat().st_size for p in pdfs)
    print(f"[1/4] found    {len(pdfs)} PDF(s) in {args.folder.name}/ ({total:,} bytes)")
    for p in pdfs:
        print(f"               {p.name}")

    msg = build_message(pdfs, args.sender, recipients, args.subject)
    msgid = msg["Message-ID"]
    print(f"[2/4] built    {len(bytes(msg)):,} bytes encoded, to {', '.join(recipients)}")

    try:
        with smtplib.SMTP(args.host, args.port, timeout=30) as smtp:
            smtp.ehlo()
            # Base64 inflates attachments by roughly a third, so a PDF well
            # under the server limit can still produce an oversized message.
            # Check against what this server actually advertises.
            limit = smtp.esmtp_features.get("size")
            if limit and limit.isdigit():
                encoded = len(bytes(msg))
                if encoded > int(limit):
                    die(
                        f"Message is {encoded:,} bytes encoded but the server accepts "
                        f"at most {int(limit):,}. Send fewer or smaller PDFs."
                    )
            smtp.send_message(msg, from_addr=args.sender, to_addrs=recipients)
    except smtplib.SMTPException as exc:
        print(f"[3/4] smtp     FAILED at {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"[3/4] smtp     cannot reach {args.host}:{args.port}: {exc}", file=sys.stderr)
        print("\nIs the container up?  docker compose ps", file=sys.stderr)
        return 1
    print(f"[3/4] smtp     submitted to {args.host}:{args.port}")

    if args.no_verify:
        print(f"[4/4] verify   skipped\n\nInbox: {web_base}")
        return 0

    try:
        rc = verify(web_base, msgid, pdfs)
    except (urllib.error.URLError, OSError) as exc:
        print(f"[4/4] verify   could not reach the API at {web_base}: {exc}", file=sys.stderr)
        return 1

    print(f"\nInbox: {web_base}")
    return rc


def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    sys.exit(main())
