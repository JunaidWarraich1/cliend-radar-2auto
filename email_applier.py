"""Direct Gmail/SMTP application sender and persistent application tracker."""

import json
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Dict

from config import APPLIED_LOG_JSON, CANDIDATE_PROFILE, RESUME_PATH
from pitch_engine import generate_track_pitch


def load_env_file(env_path: str) -> None:
    """Load simple KEY=VALUE pairs from .env if present."""
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def load_applied_log() -> Dict[str, Any]:
    """Load persistent tracking states (applied, saved, hidden, email_sent)."""
    if not os.path.exists(APPLIED_LOG_JSON):
        return {}
    try:
        with open(APPLIED_LOG_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_applied_log(log_data: Dict[str, Any]) -> None:
    """Persist application tracking states safely."""
    os.makedirs(os.path.dirname(APPLIED_LOG_JSON), exist_ok=True)
    with open(APPLIED_LOG_JSON, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2)


def update_job_status(job_id: str, action: str, value: bool = True, note: str = "") -> Dict[str, Any]:
    """Update status for a single job ID without overwriting other flags."""
    log = load_applied_log()
    entry = log.get(job_id, {})
    entry[action] = value
    if value and action in ("applied", "email_sent"):
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    if note:
        entry["note"] = note
    log[job_id] = entry
    save_applied_log(log)
    return entry


def is_smtp_configured() -> bool:
    """Return True if Gmail SMTP sender credentials exist in environment."""
    return bool(os.getenv("GMAIL_ADDRESS") and os.getenv("GMAIL_APP_PASSWORD"))


def send_application_email(job: Dict[str, Any], custom_body: str = "") -> Dict[str, Any]:
    """
    Send a tailored application email with Junaid's PDF resume attached.
    Guards strictly against duplicate sends to the same job ID or recipient.
    """
    recipient = (job.get("email") or "").strip()
    if not recipient or "@" not in recipient:
        return {"ok": False, "error": "No valid employer email address on this listing."}

    log = load_applied_log()
    job_id = str(job["id"])
    if log.get(job_id, {}).get("email_sent"):
        return {"ok": False, "error": "Application already sent to this listing."}

    sender_email = os.getenv("GMAIL_ADDRESS", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    if not sender_email or not app_password:
        return {
            "ok": False,
            "error": (
                "Gmail SMTP not configured yet. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD "
                "to .env to enable 1-click PDF resume emailing."
            ),
        }

    pitches = generate_track_pitch(job)
    body = custom_body.strip() if custom_body.strip() else pitches["short_pitch"]

    msg = EmailMessage()
    msg["Subject"] = f"Application for {job['title']} - {CANDIDATE_PROFILE['name']}"
    msg["From"] = f"{CANDIDATE_PROFILE['name']} <{sender_email}>"
    msg["To"] = recipient
    msg.set_content(body)

    if os.path.exists(RESUME_PATH):
        with open(RESUME_PATH, "rb") as rf:
            msg.add_attachment(
                rf.read(),
                maintype="application",
                subtype="pdf",
                filename="Muhammad_Junaid_Warraich_Resume.pdf",
            )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(sender_email, app_password)
            smtp.send_message(msg)
    except Exception as exc:
        return {"ok": False, "error": f"SMTP send failed: {exc}"}

    update_job_status(job_id, "email_sent", True, note=f"Sent to {recipient}")
    update_job_status(job_id, "applied", True)
    return {"ok": True, "recipient": recipient}
