import csv
import io
import json
import os
import smtplib
import zipfile
from datetime import datetime, timezone
from email.message import EmailMessage

from supabase import create_client


TO_EMAIL = os.getenv("BACKUP_EMAIL_TO", "seongkyos@gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def fetch_all_candidates(supabase):
    rows = []
    page_size = 1000
    start = 0

    while True:
        response = (
            supabase.table("candidates")
            .select("*")
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size

    return rows


def make_backup_zip(rows, timestamp):
    csv_buffer = io.StringIO()
    fieldnames = sorted({key for row in rows for key in row.keys()})

    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=fieldnames,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)

    json_data = json.dumps(rows, ensure_ascii=False, indent=2, default=str)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"candidates_{timestamp}.csv", csv_buffer.getvalue())
        zf.writestr(f"candidates_{timestamp}.json", json_data)

    return zip_buffer.getvalue()


def send_email(attachment_bytes, filename, row_count, timestamp):
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("SMTP_USER/SMTP_PASSWORD are not configured.")

    msg = EmailMessage()
    msg["Subject"] = f"리크루팅 DB 주간 백업 - {timestamp}"
    msg["From"] = SMTP_USER
    msg["To"] = TO_EMAIL
    msg.set_content(
        f"리크루팅 DB 주간 백업입니다.\n\n"
        f"- 백업 시각(UTC): {timestamp}\n"
        f"- candidates 레코드 수: {row_count}\n"
        f"- 첨부파일: {filename}\n"
    )
    msg.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="zip",
        filename=filename,
    )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(msg)


def run_backup():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL/SUPABASE_KEY are not configured.")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    rows = fetch_all_candidates(supabase)
    filename = f"recruit_db_backup_{timestamp}.zip"
    attachment = make_backup_zip(rows, timestamp)
    send_email(attachment, filename, len(rows), timestamp)


def main():
    run_backup()


if __name__ == "__main__":
    main()
