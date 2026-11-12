"""Wide-spectrum direct-apply job scanner and track classifier for Global Apply Hub."""

import concurrent.futures
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from config import (
    ARBEITNOW_API,
    BLOCKED_DOMAINS,
    DIRECT_ATS_BOARDS,
    EXCLUDE_TITLE_PATTERNS,
    GEO_REJECT_PATTERNS,
    GLOBAL_REMOTE_TERMS,
    HN_ALGOLIA_STORIES_URL,
    ON_SITE_WORKPLACE_PATTERNS,
    OPPORTUNITIES_JSON,
    PREFERRED_ATS_DOMAINS,
    PYTHON_ORG_RSS,
    TRACK_RULES,
    WORKING_NOMADS_API,
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}

SEEKER_MARKERS = (
    "seeking work",
    "open to work",
    "looking for my next",
    "looking for a new role",
    "willing to relocate:",
    "résumé/cv",
    "resume/cv",
    "available for full-time",
    "available for freelance",
)

RESTRICTED_LOCATION_TOKENS = (
    "united states",
    "usa",
    "americas",
    "amer",
    "north america",
    "latam",
    "latin america",
    "canada",
    "united kingdom",
    "europe",
    "germany",
    "france",
    "poland",
    "spain",
    "india",
    "australia",
    "brazil",
    "singapore",
    "japan",
    "switzerland",
    "zurich",
    "netherlands",
    "amsterdam",
    "austria",
    "ireland",
    "dublin",
)


def clean_html(raw_html: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not raw_html:
        return ""
    unescaped = html.unescape(raw_html)
    text = re.sub(r"<[^>]+>", " ", unescaped)
    return re.sub(r"\s+", " ", text).strip()


def parse_iso_timestamp(value: Optional[str]) -> float:
    """Convert an ISO-8601 date string into a UTC Unix timestamp."""
    if not value:
        return 0.0
    try:
        normalized = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def is_blocked_url(url: str) -> bool:
    """Return True if URL belongs to a paywalled site, gated marketplace, or resume link."""
    if not url:
        return True
    low = url.lower().strip()
    if low.startswith("mailto:"):
        return False
    try:
        parsed = urllib.parse.urlparse(low)
        host = parsed.netloc.removeprefix("www.")
        path = parsed.path
    except Exception:
        return True

    if not host:
        return True
    if any(host == dom or host.endswith("." + dom) for dom in BLOCKED_DOMAINS):
        return True
    if "/resume" in path or "/cv" in path:
        return True
    if host == "github.com" and path.count("/") <= 2 and not any(w in path for w in ("career", "job", "hiring")):
        return True
    return False


def normalize_url_key(url: str) -> str:
    """Normalize URL by stripping UTM parameters for clean deduplication."""
    if not url:
        return ""
    low = url.strip()
    if low.lower().startswith("mailto:"):
        return low.split("?")[0].lower()
    try:
        parsed = urllib.parse.urlparse(low)
        pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
        filtered = [(k, v) for k, v in pairs if not k.lower().startswith("utm_") and k.lower() not in ("ref", "source", "gh_src")]
        clean_q = urllib.parse.urlencode(filtered)
        host = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.rstrip("/").lower()
        return f"{host}{path}?{clean_q}" if clean_q else f"{host}{path}"
    except Exception:
        return low.lower()


def normalize_text_key(text: str) -> str:
    """Strip non-alphanumeric chars for company+title deduplication."""
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def classify_geo(
    title: str,
    location: str,
    description: str,
    is_remote_flag: bool = False,
) -> Tuple[bool, str]:
    """Ensure remote eligibility from Pakistan (UTC+5) and exclude US/EU/on-site traps."""
    loc_lower = (location or "").lower().strip()
    title_lower = (title or "").lower()
    intro_lower = (description or "")[:700].lower()
    header_text = f"{title_lower} | {loc_lower} | {intro_lower}"

    title_loc = f"{title_lower} | {loc_lower}"
    for pattern in ON_SITE_WORKPLACE_PATTERNS:
        if re.search(pattern, title_loc):
            return False, "restricted"

    for pattern in GEO_REJECT_PATTERNS:
        if re.search(pattern, header_text):
            return False, "restricted"

    if re.search(r"\b(?:role is|position is|is strictly)\s+(?:hybrid|on[- ]?site|in[- ]?office)\b", intro_lower):
        return False, "restricted"

    has_global_override = any(term in loc_lower for term in GLOBAL_REMOTE_TERMS)
    has_tz_overlap = "remote" in loc_lower and any(tz in loc_lower for tz in ("overlap", "cet", "gmt", "utc"))
    if loc_lower and not has_global_override and not has_tz_overlap:
        if any(re.search(r"\b" + re.escape(tok) + r"\b", loc_lower) for tok in RESTRICTED_LOCATION_TOKENS):
            return False, "restricted"
        if re.search(r"(?:^|[,;\-\s/])(?:us|uk|eu|ca|de|fr)(?:$|[,;\-\s/])", loc_lower):
            return False, "restricted"

    combined = f"{title_lower} {loc_lower} {intro_lower}"
    has_remote = is_remote_flag or any(
        w in combined
        for w in ("remote", "worldwide", "anywhere", "home based", "distributed", "async", "telecommute")
    )
    if not has_remote:
        return False, "non-remote"

    if any(w in combined for w in ("worldwide", "global", "anywhere", "work from anywhere", "home based - worldwide")):
        return True, "Worldwide"
    if any(w in combined for w in ("emea", "apac", "pakistan", "async", "utc+5")):
        return True, "EMEA / APAC"
    return True, "Remote (Unrestricted)"


def compute_freshness(published_ts: float, is_evergreen_ats: bool = False) -> Tuple[bool, int, str]:
    """Compute posting age in days."""
    if not published_ts or published_ts <= 0:
        return True, 14, "Active"
    seconds_old = max(0.0, time.time() - float(published_ts))
    days_old = int(seconds_old // 86400)
    if is_evergreen_ats:
        if days_old > 30:
            return True, 15, "Active ATS"
    elif days_old > 35:
        return False, days_old, f"{days_old}d ago"

    if days_old == 0:
        hrs = max(1, int(seconds_old // 3600))
        return True, 0, f"{hrs}h ago" if hrs < 24 else "Today"
    if days_old == 1:
        return True, 1, "1d ago"
    return True, days_old, f"{days_old}d ago"


def is_seeker_comment(raw_text: str) -> bool:
    """Filter out developer resumes accidentally posted inside 'Who is hiring?' threads."""
    low = raw_text.lower()
    if any(marker in low for marker in SEEKER_MARKERS):
        return True
    if "location:" in low[:200] and "technologies:" in low[:400]:
        return True
    if re.search(r"\bi(?:'m| am) (?:a |an )?(?:software|full[- ]?stack|backend|python).{0,40}\blooking for\b", low[:350]):
        return True
    return False


def parse_hn_header(comment_html: str) -> Tuple[str, str, str]:
    """Extract (company, title, location) from an HN 'Who is hiring?' comment."""
    first_para = re.split(r"<p>", comment_html, maxsplit=1, flags=re.IGNORECASE)[0]
    first_line = clean_html(first_para)
    if len(first_line) > 220:
        first_line = first_line.split(". ")[0]
    parts = [p.strip() for p in re.split(r"\s*\|\s*", first_line) if p.strip()]
    if not parts:
        return "Startup Team", "Software / Tech Role", ""

    company = parts[0][:65].strip()
    if "http" in company.lower() or len(company) < 2:
        company = "Startup Team"

    title = ""
    loc_tokens: List[str] = []
    for token in parts[1:]:
        t_low = token.lower()
        if any(g in t_low for g in ("remote", "onsite", "on-site", "hybrid", "emea", "apac", "worldwide", "global", "us ", "usa", "uk", "eu", "nyc", "sf", "london", "berlin")):
            loc_tokens.append(token)
            if not any(w in t_low for w in ("engineer", "support", "qa", "analyst", "developer", "operations", "legal", "specialist")):
                continue
        if not title and len(token) <= 95 and not token.startswith("$") and "http" not in t_low:
            title = token

    if not title:
        title = "Startup Tech & Ops Role"
    return company, title[:95], " | ".join(loc_tokens)


def select_best_hn_apply_target(unescaped_html: str, raw_text: str) -> Tuple[Optional[str], str, str]:
    """Pick the cleanest direct ATS, career link, or founder email from an HN comment."""
    hrefs = re.findall(r'href="(https?://[^"]+)"', unescaped_html, flags=re.IGNORECASE)
    plains = re.findall(r"https?://[^\s<>\"\'\)]+", raw_text)
    candidates: List[str] = []
    seen = set()
    for u in hrefs + plains:
        cu = u.rstrip(".,;:)")
        if cu not in seen:
            seen.add(cu)
            candidates.append(cu)

    emails = [
        e for e in re.findall(r"[\w\.\-+]+@[\w\.-]+\.\w{2,}", raw_text)
        if not any(s in e.lower() for s in ("example.com", "noreply@", "no-reply@"))
    ]
    email_addr = emails[0] if emails else ""

    best_url, best_rank, best_type = None, -1, "company"
    for u in candidates:
        if is_blocked_url(u):
            continue
        low = u.lower()
        host = urllib.parse.urlparse(low).netloc
        if any(ats in host for ats in PREFERRED_ATS_DOMAINS):
            rank, atype = 100, "ats"
        elif any(k in low for k in ("/career", "/job", "/apply", "/hiring", "careers.", "jobs.")):
            rank, atype = 75, "company"
        else:
            rank, atype = 35, "company"
        if rank > best_rank:
            best_url, best_rank, best_type = u, rank, atype

    if email_addr and best_rank < 75:
        return f"mailto:{email_addr}", "email", email_addr
    if best_url:
        return best_url, best_type, email_addr
    if email_addr:
        return f"mailto:{email_addr}", "email", email_addr
    return None, "", ""


def discover_hn_story_ids() -> List[str]:
    """Auto-discover latest monthly 'Ask HN: Who is hiring?' threads."""
    try:
        req = urllib.request.Request(HN_ALGOLIA_STORIES_URL, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ids = [str(h["objectID"]) for h in data.get("hits", []) if h.get("objectID")]
            if ids:
                return ids
    except Exception:
        pass
    return ["50338728", "49922569"]


def fetch_hacker_news() -> List[Dict[str, Any]]:
    """Fetch wide startup postings from HN monthly threads."""
    jobs: List[Dict[str, Any]] = []
    for s_id in discover_hn_story_ids():
        try:
            url = f"https://hn.algolia.com/api/v1/search_by_date?tags=comment,story_{s_id}&hitsPerPage=300"
            req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
            with urllib.request.urlopen(req, timeout=14) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for hit in data.get("hits", []):
                    if str(hit.get("parent_id")) != str(s_id):
                        continue
                    c_html = hit.get("comment_text", "")
                    if not c_html:
                        continue
                    raw_text = clean_html(c_html)
                    if is_seeker_comment(raw_text):
                        continue
                    unescaped = html.unescape(c_html)
                    company, title, loc = parse_hn_header(unescaped)
                    apply_url, apply_type, email_addr = select_best_hn_apply_target(unescaped, raw_text)
                    if not apply_url:
                        continue
                    jobs.append({
                        "id": f"hn_{hit.get('objectID')}",
                        "title": title,
                        "company": company,
                        "url": apply_url,
                        "email": email_addr,
                        "apply_type": apply_type,
                        "location": loc,
                        "is_remote": "remote" in loc.lower() or "remote" in raw_text[:400].lower(),
                        "is_evergreen_ats": False,
                        "published_ts": float(hit.get("created_at_i") or 0),
                        "description": raw_text[:1800],
                        "source": "Hacker News (Direct Startup)",
                    })
        except Exception as exc:
            print(f"[Warning] HN fetch error ({s_id}): {exc}")
    return jobs


def fetch_greenhouse_board(slug: str, company_name: str) -> List[Dict[str, Any]]:
    """Fetch all open roles from a Greenhouse board."""
    jobs: List[Dict[str, Any]] = []
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=14) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("jobs", []):
                title = (item.get("title") or "").strip()
                apply_url = (item.get("absolute_url") or "").strip()
                loc_obj = item.get("location") or {}
                location = (loc_obj.get("name") if isinstance(loc_obj, dict) else str(loc_obj)).strip()
                if title and apply_url:
                    jobs.append({
                        "id": f"gh_{slug}_{item.get('id')}",
                        "title": title,
                        "company": company_name,
                        "url": apply_url,
                        "email": "",
                        "apply_type": "ats",
                        "location": location,
                        "is_remote": "remote" in location.lower() or "home based" in location.lower(),
                        "is_evergreen_ats": True,
                        "published_ts": parse_iso_timestamp(item.get("updated_at")),
                        "description": clean_html(item.get("content") or "")[:1800],
                        "source": "Direct ATS (Greenhouse)",
                    })
    except Exception as exc:
        print(f"[Warning] Greenhouse '{slug}' error: {exc}")
    return jobs


def fetch_ashby_board(slug: str, company_name: str) -> List[Dict[str, Any]]:
    """Fetch all open roles from an Ashby board."""
    jobs: List[Dict[str, Any]] = []
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=14) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("jobs", []):
                title = (item.get("title") or "").strip()
                apply_url = (item.get("applyUrl") or item.get("jobUrl") or "").strip()
                location = (item.get("location") or "").strip()
                is_rem = bool(item.get("isRemote")) or "remote" in location.lower() or "global" in location.lower()
                if title and apply_url:
                    jobs.append({
                        "id": f"ashby_{slug}_{item.get('id', apply_url)}",
                        "title": title,
                        "company": company_name,
                        "url": apply_url,
                        "email": "",
                        "apply_type": "ats",
                        "location": location,
                        "is_remote": is_rem,
                        "is_evergreen_ats": True,
                        "published_ts": parse_iso_timestamp(item.get("publishedAt")),
                        "description": clean_html(item.get("descriptionHtml") or item.get("descriptionPlain") or "")[:1800],
                        "source": "Direct ATS (Ashby)",
                    })
    except Exception as exc:
        print(f"[Warning] Ashby '{slug}' error: {exc}")
    return jobs


def resolve_working_nomads_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Follow WorkingNomads redirect directly to employer URL, dropping middlemen."""
    go_url = (item.get("url") or "").strip()
    if not go_url:
        return None
    try:
        req = urllib.request.Request(go_url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=7) as resp:
            final_url = resp.geturl()
    except Exception:
        return None
    if is_blocked_url(final_url):
        return None
    apply_type = "ats" if any(ats in final_url.lower() for ats in PREFERRED_ATS_DOMAINS) else "company"
    return {
        "id": f"wn_{normalize_url_key(final_url)}",
        "title": (item.get("title") or "").strip(),
        "company": (item.get("company_name") or "Remote Company").strip(),
        "url": final_url,
        "email": "",
        "apply_type": apply_type,
        "location": (item.get("location") or "").strip(),
        "is_remote": True,
        "is_evergreen_ats": False,
        "published_ts": parse_iso_timestamp(item.get("pub_date")),
        "description": clean_html(item.get("description") or "")[:1800],
        "source": "WorkingNomads (Direct Link)",
    }


def fetch_working_nomads() -> List[Dict[str, Any]]:
    """Fetch wide remote jobs (Support, Ops, QA, Dev, Writing) from WorkingNomads."""
    items: List[Dict[str, Any]] = []
    try:
        req = urllib.request.Request(WORKING_NOMADS_API, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            items = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"[Warning] WorkingNomads failed: {exc}")
        return []

    jobs: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(resolve_working_nomads_item, items[:35]):
            if res:
                jobs.append(res)
    return jobs


def fetch_python_org_detail(meta: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Verify remote/telecommuting and extract direct company contact on Python.org."""
    link, title, desc = meta["link"], meta["title"], meta["description"]
    company = "Python Team"
    cleaned = re.sub(r",\s*(?:Inc\.?|LLC|Ltd\.?|GmbH|Corp\.?|Pvt\.?)$", "", title, flags=re.I)
    if "," in cleaned:
        parts = [p.strip() for p in cleaned.rsplit(",", 1)]
        if len(parts) == 2 and parts[1]:
            title, company = parts[0], parts[1]

    direct_url, email_addr, apply_type = link, "", "company"
    is_remote = "remote" in (title + " " + desc).lower()
    try:
        req = urllib.request.Request(link, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            p_html = resp.read().decode("utf-8", errors="ignore")
            if "telecommuting" in p_html.lower() or "remote" in p_html.lower():
                is_remote = True
            block_m = re.search(r"Contact Info.*?</div>", p_html, re.S | re.I)
            if block_m:
                blk = block_m.group(0)
                for u in re.findall(r'href="(https?://[^"]+)"', blk, re.I):
                    if not is_blocked_url(u) and "python.org" not in u.lower():
                        direct_url = u
                        apply_type = "ats" if any(a in u.lower() for a in PREFERRED_ATS_DOMAINS) else "company"
                        break
                emails = [
                    e for e in re.findall(r"[\w\.\-+]+@[\w\.-]+\.\w{2,}", clean_html(blk))
                    if "python.org" not in e.lower() and "usetheapply" not in e.lower()
                ]
                if emails:
                    email_addr = emails[0]
                    if direct_url == link:
                        direct_url, apply_type = f"mailto:{email_addr}", "email"
    except Exception:
        pass

    if is_blocked_url(direct_url):
        return None
    return {
        "id": f"pyorg_{link}",
        "title": title,
        "company": company,
        "url": direct_url,
        "email": email_addr,
        "apply_type": apply_type,
        "location": "Remote" if is_remote else "",
        "is_remote": is_remote,
        "is_evergreen_ats": False,
        "published_ts": 0.0,
        "description": desc[:1800],
        "source": "Python.org Official Board",
    }


def fetch_python_org() -> List[Dict[str, Any]]:
    """Fetch official Python jobs RSS."""
    raw: List[Dict[str, str]] = []
    try:
        req = urllib.request.Request(PYTHON_ORG_RSS, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            root = ET.fromstring(resp.read())
            for it in root.findall(".//item")[:20]:
                t = (it.findtext("title") or "").strip()
                l = (it.findtext("link") or "").strip()
                d = clean_html(it.findtext("description") or "")
                if t and l:
                    raw.append({"title": t, "link": l, "description": d})
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(fetch_python_org_detail, raw):
            if res:
                out.append(res)
    return out


def fetch_arbeitnow() -> List[Dict[str, Any]]:
    """Fetch remote jobs across wide fields from Arbeitnow."""
    jobs: List[Dict[str, Any]] = []
    try:
        req = urllib.request.Request(ARBEITNOW_API, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            for item in json.loads(resp.read().decode("utf-8")).get("data", []):
                if not item.get("remote"):
                    continue
                url = (item.get("url") or "").strip()
                if not url or is_blocked_url(url):
                    continue
                jobs.append({
                    "id": f"arb_{item.get('slug', url)}",
                    "title": (item.get("title") or "").strip(),
                    "company": (item.get("company_name") or "Remote Team").strip(),
                    "url": url,
                    "email": "",
                    "apply_type": "company",
                    "location": f"Remote ({item.get('location', 'Global')})",
                    "is_remote": True,
                    "is_evergreen_ats": False,
                    "published_ts": float(item.get("created_at") or 0),
                    "description": clean_html(item.get("description") or "")[:1800],
                    "source": "Arbeitnow Remote",
                })
    except Exception:
        pass
    return jobs


def evaluate_wide_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Classify and score any accessible lower-competition remote job."""
    rejected = {"eligible": False}
    title = (job.get("title") or "").strip()
    t_low = title.lower()
    desc = (job.get("description") or "").strip()
    d_low = desc.lower()
    loc = (job.get("location") or "").strip()

    if not title or len(title) > 160:
        return rejected

    # Reject impossible senior/executive, foreign-language-locked, or hardware roles
    for pat in EXCLUDE_TITLE_PATTERNS:
        if re.search(pat, t_low):
            return rejected

    # Also skip roles marked Senior unless they're direct startup/support/legal/QA where Junaid can compete
    if re.search(r"\b(french|japanese|german|spanish|korean|mandarin|arabic)\b", t_low):
        return rejected

    geo_ok, geo_label = classify_geo(
        title=title,
        location=loc,
        description=desc,
        is_remote_flag=bool(job.get("is_remote")),
    )
    if not geo_ok:
        return rejected

    fresh_ok, days_old, freshness_label = compute_freshness(
        published_ts=float(job.get("published_ts") or 0),
        is_evergreen_ats=bool(job.get("is_evergreen_ats")),
    )
    if not fresh_ok:
        return rejected

    # Match against the 5 accessible tracks
    matched_track = None
    best_bonus = 0
    for track_name, rule in TRACK_RULES.items():
        if any(term in t_low for term in rule["terms"]):
            matched_track = track_name
            best_bonus = rule["competition_bonus"]
            break

    # Secondary check on description only if title was generic, skipping Legal-Tech boilerplate false positives
    if not matched_track:
        for track_name, rule in TRACK_RULES.items():
            if track_name == "Legal-Tech & Compliance":
                continue
            if any(term in d_low[:400] for term in rule["terms"]):
                matched_track = track_name
                best_bonus = rule["competition_bonus"]
                break

    if not matched_track:
        return rejected

    # Accessibility & Ease-of-Landing Score (0-100)
    ease_score = 45 + best_bonus

    is_entry_friendly = any(
        w in t_low
        for w in ("junior", "entry", "associate", "graduate", "apprentice", "coordinator", "assistant", "specialist", "support", "qa", "test")
    )
    is_senior = any(w in t_low for w in ("senior", "sr.", "sr ", "lead "))

    if is_entry_friendly:
        ease_score += 15
        competition_label = "Lower Competition"
    elif job.get("apply_type") == "email":
        ease_score += 14
        competition_label = "Direct Email (Fast Reply)"
    elif is_senior:
        ease_score -= 10
        competition_label = "Higher Bar (Worth Trying)"
    else:
        ease_score += 6
        competition_label = "Moderate Competition"

    if geo_label == "Worldwide":
        ease_score += 8
    elif geo_label == "EMEA / APAC":
        ease_score += 5

    if days_old <= 2:
        ease_score += 10
    elif days_old <= 7:
        ease_score += 5

    return {
        "eligible": True,
        "track": matched_track,
        "ease_score": min(99, max(20, ease_score)),
        "competition_label": competition_label,
        "geo_label": geo_label,
        "freshness_label": freshness_label,
        "days_old": days_old,
        "is_entry_friendly": is_entry_friendly,
    }


def scan_and_save() -> List[Dict[str, Any]]:
    """Run full concurrent scan, filter, score, and persist opportunities.json."""
    raw: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as ex:
        futures = [
            ex.submit(fetch_hacker_news),
            ex.submit(fetch_python_org),
            ex.submit(fetch_working_nomads),
            ex.submit(fetch_arbeitnow),
        ]
        for slug, name in DIRECT_ATS_BOARDS["greenhouse"]:
            futures.append(ex.submit(fetch_greenhouse_board, slug, name))
        for slug, name in DIRECT_ATS_BOARDS["ashby"]:
            futures.append(ex.submit(fetch_ashby_board, slug, name))
        for f in concurrent.futures.as_completed(futures):
            try:
                raw.extend(f.result())
            except Exception:
                pass

    # Deduplicate cleanly keeping highest-priority apply route (email > ats > company)
    prio = {"email": 3, "ats": 2, "company": 1}
    raw.sort(
        key=lambda j: (prio.get(j.get("apply_type", "company"), 0), float(j.get("published_ts") or 0)),
        reverse=True,
    )

    seen_urls, seen_ct = set(), set()
    opportunities: List[Dict[str, Any]] = []
    for job in raw:
        uk = normalize_url_key(job.get("url", ""))
        ct = (normalize_text_key(job.get("company", "")), normalize_text_key(job.get("title", "")))
        if (uk and uk in seen_urls) or (ct[0] and ct[1] and ct in seen_ct):
            continue

        ev = evaluate_wide_job(job)
        if not ev["eligible"]:
            continue

        if uk:
            seen_urls.add(uk)
        if ct[0] and ct[1]:
            seen_ct.add(ct)

        opportunities.append({
            "id": job["id"],
            "title": job["title"],
            "company": job["company"],
            "url": job["url"],
            "email": job.get("email", ""),
            "apply_type": job.get("apply_type", "company"),
            "location": job.get("location", ""),
            "description": job.get("description", ""),
            "source": job.get("source", ""),
            "track": ev["track"],
            "ease_score": ev["ease_score"],
            "competition_label": ev["competition_label"],
            "geo_label": ev["geo_label"],
            "freshness_label": ev["freshness_label"],
            "days_old": ev["days_old"],
            "is_entry_friendly": ev["is_entry_friendly"],
        })

    opportunities.sort(key=lambda x: (x["ease_score"], -x["days_old"]), reverse=True)
    os.makedirs(os.path.dirname(OPPORTUNITIES_JSON), exist_ok=True)
    with open(OPPORTUNITIES_JSON, "w", encoding="utf-8") as f:
        json.dump(opportunities, f, indent=2)
    return opportunities
