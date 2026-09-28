import csv
import io
import json
import os
import smtplib
import zipfile
from datetime import datetime, timezone
from email.message import EmailMessage

from supabase import create_client


# Render Cron Job에서 실행되는 주간 Supabase 백업
# 기본 수신 주소는 사용자가 지정한 주소이며, 필요하면 Render 환경변수로 변경할 수 있습니다.
TO_EMAIL = os.getenv("BACKUP_EMAIL_TO", "seongkyos@gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def fetch_all_candidates(supabase):
    """Supabase 기본 반환 제한에 걸리지 않도록 candidates 전체를 페이지 단위로 가져옵니다."""
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
    """CSV와 JSON을 하나의 ZIP 파일로 만들어 메일 첨부용 bytes로 반환합니다."""
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
        raise RuntimeError(
            "SMTP_USER와 SMTP_PASSWORD 환경변수가 필요합니다. "
            "Gmail 앱 비밀번호를 Render 환경변수에 등록하세요."
        )

    msg = EmailMessage()
    msg["Subject"] = f"리크루팅 DB 주간 백업 - {timestamp}"
    msg["From"] = SMTP_USER
    msg["To"] = TO_EMAIL
    msg.set_content(
        f"리크루팅 DB 주간 백업입니다.\n\n"
        f"- 백업 시각(UTC): {timestamp}\n"
        f"- candidates 레코드 수: {row_count}\n"
        f"- 첨부파일: {filename}\n\n"
        "첨부 ZIP 안에 CSV와 JSON 백업이 들어 있습니다."
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


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL과 SUPABASE_KEY 환경변수가 필요합니다.")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    rows = fetch_all_candidates(supabase)
    filename = f"recruit_db_backup_{timestamp}.zip"
    attachment = make_backup_zip(rows, timestamp)

    send_email(attachment, filename, len(rows), timestamp)

    print(f"OK: {len(rows)}개 레코드 백업을 {TO_EMAIL}으로 발송했습니다.")


if __name__ == "__main__":
    main()
