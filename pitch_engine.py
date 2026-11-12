"""Track-aware pitch and email drafting engine tailored to lower-competition roles."""

import urllib.parse
from typing import Any, Dict

from config import CANDIDATE_PROFILE


def generate_track_pitch(job: Dict[str, Any]) -> Dict[str, str]:
    """Generate both a short direct pitch and an ATS cover note matched to the role track."""
    p = CANDIDATE_PROFILE
    company = job.get("company", "the team")
    title = job.get("title", "Remote Role")
    track = job.get("track", "Junior / Entry & Automation")

    if track == "Tech Support & Solutions":
        angle = (
            "With hands-on software engineering experience at Enigmatix and strong English communication, "
            "I excel at debugging REST APIs, writing SQL diagnostics, reproducing edge-case bugs, and guiding "
            "customers clearly to resolution."
        )
        highlights = (
            "- Debugged full-stack Python/FastAPI and React applications in production.\n"
            "- Comfortable inspecting HTTP logs, database queries (PostgreSQL/SQL), and JSON payloads.\n"
            "- Reliable across EMEA, APAC, and US time-zone overlap with fast, clear written updates."
        )
    elif track == "Legal-Tech & Compliance":
        angle = (
            f"Holding a dual academic background in {p['education']}, I bring both analytical legal training "
            "(contracts, privacy, regulatory review) and hands-on technical fluency in APIs and data systems."
        )
        highlights = (
            "- Rare blend of LLB legal reasoning and Bachelor of Computer Science technical execution.\n"
            "- Experienced implementing strict RBAC access controls, audit trails, and GDPR-conscious data validation.\n"
            "- Strong documentation, structured policy analysis, and cross-team communication."
        )
    elif track == "QA & Software Testing":
        angle = (
            "At Enigmatix and in my flagship project WorkFlow Pro, I focused heavily on negative-path testing, "
            "API boundary validation, and automated regression suites to catch bugs before release."
        )
        highlights = (
            "- Built isolated automated test suites using Pytest covering permissions, edge cases, and concurrency.\n"
            "- Methodical at reproducing UI/API defects, writing clear bug reports, and verifying fixes.\n"
            "- Comfortable testing both web frontends (React) and backend REST services."
        )
    elif track == "Data, Research & Operations":
        angle = (
            "As a Computer Science and Law graduate with software house experience at Enigmatix, "
            "I combine strong analytical research skills with Python and SQL automation to keep operations fast and accurate."
        )
        highlights = (
            "- Proficient in Python scripting, data cleaning, PostgreSQL/SQL queries, and structured reporting.\n"
            "- Detail-oriented writer and researcher capable of owning documentation, operations, and coordination.\n"
            "- Available immediately for full-time or flexible remote schedules."
        )
    else:
        angle = (
            "As a Full-Stack & Python Engineer (ex-Enigmatix), I build clean backend APIs, "
            "automation scripts, and responsive web interfaces with automated test coverage."
        )
        highlights = (
            f"- Built WorkFlow Pro ({p['workflow_pro']}) using Python/FastAPI, PostgreSQL, and React 18.\n"
            "- Strong foundation in REST APIs, database schemas, Docker, and Git workflows.\n"
            "- Fast learner ready to take on immediate engineering, scripting, or implementation tasks."
        )

    short_pitch = (
        f"Hi {company} team,\n\n"
        f"I'm {p['name']} ({p['education']}) applying for the {title} opening. {angle}\n\n"
        f"Portfolio: {p['portfolio']} | GitHub: {p['github']} | LinkedIn: {p['linkedin']}\n\n"
        f"Available to start immediately. Would welcome a quick chat!\n"
        f"Best regards,\n{p['name']} | {p['phone']} | {p['email']}"
    )

    cover_note = (
        f"Subject: Application for {title} - {p['name']}\n\n"
        f"Dear {company} Hiring Team,\n\n"
        f"I am excited to apply for the {title} position. {angle}\n\n"
        f"Key Relevant Strengths:\n{highlights}\n\n"
        f"Links & Resume Verification:\n"
        f"- Portfolio: {p['portfolio']}\n"
        f"- Live Project (WorkFlow Pro): {p['workflow_pro']}\n"
        f"- GitHub: {p['github']}\n"
        f"- LinkedIn: {p['linkedin']}\n\n"
        f"Thank you for your time and consideration. I am available immediately for remote work.\n\n"
        f"Sincerely,\n{p['name']}\n{p['phone']} | {p['email']}"
    )

    return {
        "short_pitch": short_pitch,
        "cover_note": cover_note,
    }


def build_mailto_url(email: str, title: str, short_pitch: str) -> str:
    """Create a pre-filled mailto: link for instant one-tap mobile/desktop emailing."""
    subject = urllib.parse.quote(f"Application for {title} - {CANDIDATE_PROFILE['name']}")
    body = urllib.parse.quote(short_pitch)
    return f"mailto:{email}?subject={subject}&body={body}"
