"""Unit tests for Global Apply Hub."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import email_applier
from app import app, build_autofill_bookmarklet
from fastapi.testclient import TestClient
from pitch_engine import generate_track_pitch
from scanner import evaluate_wide_job


def test_accessible_tracks_and_foreign_language_rejection():
    """Verify wide lower-competition tracks pass while foreign-language or US-only roles drop."""
    support_job = {
        "id": "1",
        "title": "Associate Technical Support Engineer",
        "company": "PostHog",
        "url": "https://jobs.ashbyhq.com/posthog/1",
        "email": "",
        "apply_type": "ats",
        "location": "Remote",
        "is_remote": True,
        "is_evergreen_ats": True,
        "published_ts": 0,
        "description": "Help developers debug APIs remotely worldwide.",
        "source": "Direct ATS",
    }
    res_sup = evaluate_wide_job(support_job)
    assert res_sup["eligible"] is True
    assert res_sup["track"] == "Tech Support & Solutions"

    legal_job = {
        **support_job,
        "id": "2",
        "title": "Legal Operations Specialist",
        "description": "Manage contracts and privacy compliance globally.",
    }
    res_leg = evaluate_wide_job(legal_job)
    assert res_leg["eligible"] is True
    assert res_leg["track"] == "Legal-Tech & Compliance"

    french_job = {
        **support_job,
        "id": "3",
        "title": "Enterprise Customer Success (French speaker)",
    }
    assert evaluate_wide_job(french_job)["eligible"] is False

    us_only_job = {
        **support_job,
        "id": "4",
        "location": "Remote - US Only",
    }
    assert evaluate_wide_job(us_only_job)["eligible"] is False


def test_track_specific_pitches_highlight_right_strengths():
    """Verify Legal-Tech mentions LLB and Support mentions API debugging."""
    legal_pitch = generate_track_pitch({
        "title": "Compliance Specialist",
        "company": "Acme",
        "track": "Legal-Tech & Compliance",
    })
    assert "LLB" in legal_pitch["short_pitch"]

    support_pitch = generate_track_pitch({
        "title": "Support Engineer",
        "company": "Acme",
        "track": "Tech Support & Solutions",
    })
    assert "REST APIs" in support_pitch["short_pitch"]


def test_email_applier_guards_missing_credentials_and_duplicates(tmp_path, monkeypatch):
    """Email sender must fail cleanly without SMTP creds and block duplicate sends."""
    temp_log = tmp_path / "applied_log.json"
    monkeypatch.setattr(email_applier, "APPLIED_LOG_JSON", str(temp_log))
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)

    job = {
        "id": "hn_999",
        "title": "Junior QA Engineer",
        "company": "Startup",
        "email": "jobs@startup.test",
        "track": "QA & Software Testing",
    }
    res = email_applier.send_application_email(job)
    assert res["ok"] is False
    assert "not configured" in res["error"]

    email_applier.save_applied_log({"hn_999": {"email_sent": True}})
    res_dup = email_applier.send_application_email(job)
    assert res_dup["ok"] is False
    assert "already sent" in res_dup["error"]


def test_bookmarklet_and_status_endpoint(tmp_path, monkeypatch):
    """Verify bookmarklet contains candidate links and status endpoint validates actions."""
    bm = build_autofill_bookmarklet()
    assert bm.startswith("javascript:")
    assert "j.warraich2004@gmail.com" in bm
    assert "muhammad-junaid-warraich-dev" in bm

    temp_log = tmp_path / "applied_log.json"
    monkeypatch.setattr(email_applier, "APPLIED_LOG_JSON", str(temp_log))

    client = TestClient(app)
    resp_ok = client.post("/api/status/job_1", json={"action": "saved", "value": True})
    assert resp_ok.status_code == 200
    assert resp_ok.json()["state"]["saved"] is True

    resp_bad = client.post("/api/status/job_1", json={"action": "invalid", "value": True})
    assert resp_bad.status_code == 400


def test_render_dashboard_local_and_static_modes():
    """Verify both local_mode=True (with email send button) and static mode render cleanly."""
    from app import render_dashboard_html

    sample_jobs = [{
        "id": "hn_email_1",
        "title": "Junior QA Tester",
        "company": "Startup Co",
        "url": "mailto:jobs@startup.test",
        "email": "jobs@startup.test",
        "apply_type": "email",
        "location": "Remote",
        "description": "Help test Python APIs.",
        "source": "Hacker News",
        "track": "QA & Software Testing",
        "ease_score": 88,
        "competition_label": "Lower Competition",
        "geo_label": "Worldwide",
        "freshness_label": "1d ago",
        "days_old": 1,
        "is_entry_friendly": True,
    }]
    html_local = render_dashboard_html(sample_jobs, {}, "2026-11-12 12:30", local_mode=True)
    assert "1-Click Send PDF Email" in html_local
    html_static = render_dashboard_html(sample_jobs, {}, "2026-11-12 12:30", local_mode=False)
    assert "Copy Auto-Fill" in html_static
