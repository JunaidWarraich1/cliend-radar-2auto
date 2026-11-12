"""Configuration and wide-role matching rules for Global Apply Hub.
Focuses on accessible, lower-competition global remote roles with zero paywalls.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESUME_PATH = os.path.join(BASE_DIR, "assets", "Muhammad_Junaid_Warraich_Resume.pdf")
OPPORTUNITIES_JSON = os.path.join(BASE_DIR, "data", "opportunities.json")
APPLIED_LOG_JSON = os.path.join(BASE_DIR, "data", "applied_log.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

CANDIDATE_PROFILE = {
    "first_name": "Muhammad Junaid",
    "last_name": "Warraich",
    "name": "Muhammad Junaid Warraich",
    "cnic_name": "Muhammad Junaid",
    "email": "j.warraich2004@gmail.com",
    "phone": "+92 348 1064513",
    "location": "Pakistan (Remote - EMEA / APAC / Worldwide)",
    "city": "Lahore",
    "country": "Pakistan",
    "linkedin": "https://www.linkedin.com/in/muhammad-junaid-warraich-dev",
    "github": "https://github.com/JunaidWarraich1",
    "portfolio": "https://myportfolio-seven-eta-43.vercel.app/",
    "workflow_pro": "https://workflow-pro-ebon.vercel.app/",
    "experience_company": "Enigmatix",
    "education": "BS Computer Science + LLB (Bachelor of Laws)",
}

HN_ALGOLIA_STORIES_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?query=%22Ask%20HN%3A%20Who%20is%20hiring%22"
    "&tags=story,author_whoishiring&hitsPerPage=2"
)

DIRECT_ATS_BOARDS = {
    "greenhouse": [
        ("canonical", "Canonical"),
        ("wikimedia", "Wikimedia Foundation"),
        ("gitlab", "GitLab"),
        ("bitwarden", "Bitwarden"),
        ("binance", "Binance"),
    ],
    "ashby": [
        ("supabase", "Supabase"),
        ("posthog", "PostHog"),
        ("railway", "Railway"),
        ("prefect", "Prefect"),
        ("elevenlabs", "ElevenLabs"),
    ],
}

PYTHON_ORG_RSS = "https://www.python.org/jobs/feed/rss/"
WORKING_NOMADS_API = "https://www.workingnomads.com/api/exposed_jobs/"
ARBEITNOW_API = "https://www.arbeitnow.com/api/job-board-api"

BLOCKED_DOMAINS = (
    "remotive.com",
    "remoteok.com",
    "remoteok.io",
    "weworkremotely.com",
    "himalayas.app",
    "wellfound.com",
    "angel.co",
    "toptal.com",
    "turing.com",
    "lemon.io",
    "micro1.ai",
    "mercor.com",
    "outlier.ai",
    "dataannotation.tech",
    "crossover.com",
    "bairesdev.com",
    "withbraintrust.com",
    "usebraintrust.com",
    "linkedin.com",
    "lnkd.in",
    "indeed.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "mercurynews.com",
    "nytimes.com",
    "wikipedia.org",
    "news.ycombinator.com",
)

PREFERRED_ATS_DOMAINS = (
    "greenhouse.io",
    "grnh.se",
    "lever.co",
    "ashbyhq.com",
    "workable.com",
    "bamboohr.com",
    "smartrecruiters.com",
    "personio.com",
    "teamtailor.com",
    "rippling.com",
    "gem.com",
    "recruitee.com",
)

GEO_REJECT_PATTERNS = [
    r"\bus[- ]only\b",
    r"\busa[- ]only\b",
    r"\bu\.s\.?[- ]only\b",
    r"\bunited states only\b",
    r"\bmust (?:be located|reside|live) in (?:the )?(?:us|usa|united states|uk|canada|eu|europe)\b",
    r"\bauthorized to work in (?:the )?(?:us|usa|u\.s\.|united states|canada|uk|eu)\b",
    r"\bwork authorization in (?:the )?(?:us|usa|u\.s\.|united states)\b",
    r"\bus citizens?(?:hip)?\b",
    r"\bsecurity clearance\b",
    r"\bclearance required\b",
    r"\bamericas only\b",
    r"\bnorth america only\b",
    r"\bcanada only\b",
    r"\buk only\b",
    r"\beu only\b",
    r"\beurope only\b",
    r"\blatam only\b",
    r"\blatin america only\b",
    r"\baustralia only\b",
    r"\bremote[- ,:/]+(?:us|usa|united states|amer|north america|latam|canada|uk|united kingdom|germany|france|poland|spain|india|singapore|japan)\b",
    r"\bremote in (?:the )?(?:us|usa|united states|uk|united kingdom|canada|eu|europe|germany|france)\b",
]

ON_SITE_WORKPLACE_PATTERNS = [
    r"\bon[- ]?site\b",
    r"\bin[- ]office\b",
    r"\bin[- ]person\b",
    r"\bhybrid\b",
]

GLOBAL_REMOTE_TERMS = (
    "worldwide",
    "global",
    "anywhere",
    "work from anywhere",
    "remote - global",
    "home based - worldwide",
    "emea",
    "apac",
    "pakistan",
    "async",
    "all-remote",
)

# Roles requiring foreign languages or non-accessible physical/executive credentials
EXCLUDE_TITLE_PATTERNS = [
    r"\b(?:french|japanese|german|spanish|korean|mandarin|cantonese|arabic|dutch|italian|portuguese|polish|turkish)\s*(?:speaker|speaking|fluent|bilingual)\b",
    r"\b(?:vp|vice president|director|head of|chief|principal|staff|distinguished)\b",
    r"\b(?:engineering manager|senior manager|cpa|chartered accountant|nurse|physician|therapist|driver)\b",
    r"\b(?:ios|android|flutter|swift|kotlin|unity|unreal|embedded|firmware|hardware|pcb|mechanical|electrical)\b",
    r"\b(?:sap|salesforce|servicenow|sharepoint|cobol)\b",
]

# Six accessible remote career tracks ranked by realistic accessibility & lower competition
TRACK_RULES = {
    "Tech Support & Solutions": {
        "terms": (
            "support engineer", "technical support", "customer support",
            "implementation", "customer success", "solutions engineer",
            "developer advocate", "support specialist", "onboarding",
        ),
        "competition_bonus": 22,
    },
    "Legal-Tech & Compliance": {
        "terms": (
            "legal", "compliance", "contract", "privacy", "policy",
            "governance", "regulatory", "paralegal", "trust & safety",
            "risk analyst", "audit",
        ),
        "competition_bonus": 24,
    },
    "QA & Software Testing": {
        "terms": (
            "qa", "quality assurance", "test engineer", "tester",
            "automation engineer", "sdet", "testing", "eval", "evaluation",
        ),
        "competition_bonus": 20,
    },
    "Data, Research & Operations": {
        "terms": (
            "data analyst", "data operations", "operations", "coordinator",
            "research", "technical writer", "documentation", "content",
            "community", "assistant", "specialist", "associate", "communications",
        ),
        "competition_bonus": 18,
    },
    "Junior / Entry & Automation": {
        "terms": (
            "junior", "entry", "graduate", "apprentice", "intern",
            "automation", "python", "fastapi", "scraping", "scripting",
            "web developer", "frontend", "react", "full-stack", "fullstack",
            "full stack", "backend", "software engineer", "developer", "product builder",
        ),
        "competition_bonus": 12,
    },
}
