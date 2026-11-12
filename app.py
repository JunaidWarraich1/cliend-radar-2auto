"""Global Apply Hub web application and static dashboard builder.
Serves local interactive applying tools (1-click PDF resume emailing, scan refresh,
and persistent status tracking) plus standalone HTML output.
"""

import html
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from config import (
    BASE_DIR,
    CANDIDATE_PROFILE,
    OPPORTUNITIES_JSON,
    OUTPUT_DIR,
    RESUME_PATH,
)
from email_applier import (
    is_smtp_configured,
    load_applied_log,
    load_env_file,
    send_application_email,
    update_job_status,
)
from pitch_engine import build_mailto_url, generate_track_pitch
from scanner import scan_and_save

load_env_file(os.path.join(BASE_DIR, ".env"))

app = FastAPI(title="Global Apply Hub", version="1.0.0")


class StatusToggleRequest(BaseModel):
    action: str
    value: bool = True


class SendEmailRequest(BaseModel):
    custom_body: str = ""


def build_autofill_bookmarklet() -> str:
    """Build a React-compatible JS bookmarklet that auto-fills ATS forms in one click."""
    p = CANDIDATE_PROFILE
    js_code = (
        "(function(){"
        f"const P={json.dumps(p)};"
        "const setVal=(el,v)=>{"
        "const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
        "const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;"
        "if(setter)setter.call(el,v);else el.value=v;"
        "el.dispatchEvent(new Event('input',{bubbles:true}));"
        "el.dispatchEvent(new Event('change',{bubbles:true}));"
        "};"
        "let filled=0;"
        "document.querySelectorAll('input,textarea').forEach(el=>{"
        "if(el.type==='hidden'||el.type==='file'||el.type==='submit'||el.disabled)return;"
        "const lbl=(el.labels&&el.labels[0]?el.labels[0].innerText:'')+' '+(el.name||'')+' '+(el.id||'')+' '+(el.placeholder||'')+' '+(el.getAttribute('aria-label')||'');"
        "const s=lbl.toLowerCase();"
        "if(s.includes('first')&&s.includes('name')){setVal(el,P.first_name);filled++;}"
        "else if(s.includes('last')&&s.includes('name')){setVal(el,P.last_name);filled++;}"
        "else if(s.includes('email')){setVal(el,P.email);filled++;}"
        "else if(s.includes('phone')||s.includes('mobile')){setVal(el,P.phone);filled++;}"
        "else if(s.includes('linkedin')){setVal(el,P.linkedin);filled++;}"
        "else if(s.includes('github')){setVal(el,P.github);filled++;}"
        "else if(s.includes('portfolio')||s.includes('website')){setVal(el,P.portfolio);filled++;}"
        "else if(s.includes('city')||s.includes('location')){setVal(el,P.city+', '+P.country);filled++;}"
        "else if(s.includes('country')){setVal(el,P.country);filled++;}"
        "else if(s.includes('company')||s.includes('employer')){setVal(el,P.experience_company);filled++;}"
        "else if(s.includes('name')&&!s.includes('company')&&!s.includes('user')){setVal(el,P.name);filled++;}"
        "});"
        "alert('Auto-filled '+filled+' fields for '+P.name+'! Check resume PDF upload & answers.');"
        "})();"
    )
    return "javascript:" + js_code


def render_dashboard_html(
    opportunities: List[Dict[str, Any]],
    applied_log: Dict[str, Any],
    timestamp: str,
    local_mode: bool = False,
) -> str:
    """Render clean, XSS-safe, mobile and desktop responsive hub UI."""
    cards: List[str] = []
    payload: Dict[str, Any] = {
        "pitches": {},
        "bookmarklet": build_autofill_bookmarklet(),
        "profile": {
            "name": CANDIDATE_PROFILE["name"],
            "email": CANDIDATE_PROFILE["email"],
            "phone": CANDIDATE_PROFILE["phone"],
            "linkedin": CANDIDATE_PROFILE["linkedin"],
            "github": CANDIDATE_PROFILE["github"],
            "portfolio": CANDIDATE_PROFILE["portfolio"],
            "workflow_pro": CANDIDATE_PROFILE["workflow_pro"],
        },
        "local_mode": local_mode,
        "smtp_ready": is_smtp_configured(),
        "initial_states": applied_log,
    }

    for job in opportunities:
        jid = str(job["id"])
        pitches = generate_track_pitch(job)
        payload["pitches"][jid] = pitches

        is_email = job.get("apply_type") == "email" and job.get("email")
        cta_href = (
            build_mailto_url(job["email"], job["title"], pitches["short_pitch"])
            if is_email
            else job["url"]
        )
        cta_text = "Email App" if is_email else ("Apply Direct (No Signup)" if job.get("apply_type") == "ats" else "Open Job Page")

        safe_id = html.escape(jid, quote=True)
        send_btn = ""
        if local_mode and is_email:
            send_btn = (
                f'<button type="button" class="btn btn-green" onclick="sendDirectEmail(\'{safe_id}\')">'
                '1-Click Send PDF Email</button>'
            )

        copy_short_btn = (
            f'<button type="button" class="btn btn-secondary" onclick="copyPitch(\'{safe_id}\', \'short\')">'
            "Copy Short Pitch</button>"
        )
        secondary_cta = send_btn if send_btn else copy_short_btn
        safe_title = html.escape(job["title"])
        safe_company = html.escape(job["company"])
        safe_source = html.escape(job["source"])
        safe_track = html.escape(job["track"])
        safe_comp = html.escape(job["competition_label"])
        safe_geo = html.escape(job["geo_label"])
        safe_fresh = html.escape(job["freshness_label"])
        safe_desc = html.escape(job["description"][:280])
        safe_href = html.escape(cta_href, quote=True)
        search_txt = html.escape(
            f"{job['title']} {job['company']} {job['track']} {job['geo_label']} {job['source']}".lower(),
            quote=True,
        )

        cards.append(
            f"""
        <article class="card"
            data-id="{safe_id}"
            data-track="{safe_track}"
            data-search="{search_txt}"
            data-score="{job['ease_score']}"
            data-days="{job['days_old']}"
            data-email="{'1' if is_email else '0'}"
            data-world="{'1' if job['geo_label'] == 'Worldwide' else '0'}">
            <div class="card-top">
                <div class="title-col">
                    <h2 class="job-title">{safe_title}</h2>
                    <p class="company">{safe_company} &bull; <span>{safe_source}</span></p>
                </div>
                <span class="score-pill">{job['ease_score']}% Fit</span>
            </div>

            <div class="badges">
                <span class="pill pill-track">{safe_track}</span>
                <span class="pill pill-lowcomp">{safe_comp}</span>
                <span class="pill pill-geo">{safe_geo}</span>
                <span class="pill pill-muted">{safe_fresh}</span>
            </div>

            <p class="snippet">{safe_desc}...</p>

            <div class="actions-main">
                <a href="{safe_href}" target="_blank" rel="noopener noreferrer" class="btn btn-primary">{cta_text} &rarr;</a>
                {secondary_cta}
            </div>

            <div class="actions-sub">
                <button type="button" class="btn-chip" onclick="copyPitch('{safe_id}', 'short')">Short Pitch</button>
                <button type="button" class="btn-chip" onclick="copyPitch('{safe_id}', 'full')">Full Cover</button>
                <button type="button" class="btn-chip st-btn" data-act="applied" onclick="toggleJob('{safe_id}', 'applied')">Applied</button>
                <button type="button" class="btn-chip st-btn" data-act="saved" onclick="toggleJob('{safe_id}', 'saved')">Save</button>
                <button type="button" class="btn-chip" onclick="toggleJob('{safe_id}', 'hidden')">Hide</button>
            </div>

            <details class="pitch-box">
                <summary>View Tailored {safe_track} Pitch</summary>
                <pre>{html.escape(pitches['short_pitch'])}</pre>
                <pre>{html.escape(pitches['cover_note'])}</pre>
            </details>
        </article>"""
        )

    bookmarklet_href = html.escape(build_autofill_bookmarklet(), quote=True)
    json_blob = json.dumps(payload).replace("</", "<\\/")

    scan_button = (
        '<button type="button" class="btn-top" id="scanBtn" onclick="runLiveScan()">Scan New Jobs</button>'
        if local_mode
        else ""
    )
    smtp_banner = ""
    if local_mode:
        if is_smtp_configured():
            smtp_banner = '<div class="status-bar ok">Gmail 1-Click PDF Resume Sender: Ready</div>'
        else:
            smtp_banner = (
                '<div class="status-bar warn">Tip: Add <code>GMAIL_ADDRESS</code> &amp; '
                '<code>GMAIL_APP_PASSWORD</code> in <code>.env</code> to send direct emails with your PDF resume in 1 click.</div>'
            )

    tracks = sorted({j["track"] for j in opportunities})
    track_options = "".join(
        f'<option value="{html.escape(t, quote=True)}">{html.escape(t)}</option>' for t in tracks
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Global Apply Hub">
    <title>Global Apply Hub - Low-Competition Remote Jobs</title>
    <style>
        :root {{
            --bg: #090e1a; --surface: #131c2e; --surface-2: #1c2840;
            --primary: #38bdf8; --green: #10b981; --amber: #f59e0b;
            --text: #f8fafc; --muted: #94a3b8; --border: #27354d;
        }}
        * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg); color: var(--text); margin: 0;
            padding: calc(14px + env(safe-area-inset-top)) 14px calc(32px + env(safe-area-inset-bottom)) 14px;
        }}
        .container {{ max-width: 920px; margin: 0 auto; }}
        header {{ border-bottom: 1px solid var(--border); padding-bottom: 14px; margin-bottom: 14px; }}
        .top-row {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }}
        h1 {{ margin: 0; font-size: 1.45rem; color: var(--primary); }}
        .top-actions {{ display: flex; gap: 8px; align-items: center; }}
        .btn-top {{
            background: var(--green); color: #042f2e; border: none; border-radius: 8px;
            padding: 7px 12px; font-weight: 800; font-size: 0.8rem; cursor: pointer;
        }}
        .count-pill {{
            background: rgba(56,189,248,0.14); color: var(--primary); border: 1px solid rgba(56,189,248,0.35);
            padding: 5px 10px; border-radius: 999px; font-size: 0.8rem; font-weight: 700;
        }}
        .subline {{ color: var(--muted); font-size: 0.8rem; margin: 6px 0 10px 0; }}
        .status-bar {{
            font-size: 0.78rem; padding: 8px 12px; border-radius: 8px; margin-bottom: 10px;
        }}
        .status-bar.ok {{ background: rgba(16,185,129,0.14); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }}
        .status-bar.warn {{ background: rgba(245,158,11,0.12); color: #fbbf24; border: 1px solid rgba(245,158,11,0.3); }}
        .autofill-box {{
            display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
            background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
            padding: 9px 12px; margin-bottom: 10px; font-size: 0.8rem;
        }}
        .bookmarklet-btn {{
            background: #6366f1; color: #fff; text-decoration: none; padding: 6px 11px;
            border-radius: 7px; font-weight: 700; font-size: 0.78rem; white-space: nowrap;
        }}
        .quick-bar {{ display: flex; gap: 6px; overflow-x: auto; padding-bottom: 6px; margin-bottom: 8px; }}
        .qchip {{
            background: var(--surface); color: #e2e8f0; border: 1px solid var(--border);
            border-radius: 8px; padding: 6px 10px; font-size: 0.75rem; font-weight: 600;
            white-space: nowrap; cursor: pointer;
        }}
        .controls {{ display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }}
        .search-box {{
            flex: 2; min-width: 180px; background: var(--surface); color: #fff;
            border: 1px solid var(--border); border-radius: 10px; padding: 9px 12px; font-size: 0.9rem;
        }}
        .select-box {{
            flex: 1; min-width: 150px; background: var(--surface); color: var(--text);
            border: 1px solid var(--border); border-radius: 10px; padding: 8px 10px; font-size: 0.82rem; font-weight: 600;
        }}
        .tabs {{ display: flex; gap: 6px; overflow-x: auto; }}
        .tab-btn {{
            background: var(--surface); color: var(--muted); border: 1px solid var(--border);
            border-radius: 999px; padding: 6px 12px; font-size: 0.8rem; font-weight: 600;
            white-space: nowrap; cursor: pointer;
        }}
        .tab-btn.active {{ background: var(--primary); color: #090e1a; border-color: var(--primary); }}
        .card {{
            background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
            padding: 16px; margin-bottom: 14px;
        }}
        .card.is-applied {{ border-color: rgba(16,185,129,0.55); background: #0f2123; }}
        .card.is-saved {{ border-color: rgba(245,158,11,0.55); }}
        .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }}
        .title-col {{ min-width: 0; flex: 1; }}
        .job-title {{ margin: 0 0 4px 0; font-size: 1.08rem; color: #fff; }}
        .company {{ margin: 0; font-size: 0.84rem; color: var(--muted); }}
        .score-pill {{
            background: rgba(16,185,129,0.16); color: #34d399; border: 1px solid rgba(16,185,129,0.35);
            border-radius: 8px; padding: 5px 9px; font-weight: 800; font-size: 0.8rem; white-space: nowrap;
        }}
        .badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }}
        .pill {{ font-size: 0.72rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; }}
        .pill-track {{ background: rgba(56,189,248,0.16); color: var(--primary); }}
        .pill-lowcomp {{ background: rgba(16,185,129,0.18); color: #34d399; }}
        .pill-geo {{ background: rgba(245,158,11,0.15); color: #fbbf24; }}
        .pill-muted {{ background: var(--surface-2); color: var(--muted); }}
        .snippet {{ font-size: 0.85rem; line-height: 1.48; color: #cbd5e1; margin: 12px 0; }}
        .actions-main {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px; }}
        .btn {{
            display: inline-flex; align-items: center; justify-content: center; text-decoration: none;
            font-weight: 700; font-size: 0.86rem; padding: 10px 12px; border-radius: 10px; border: none; cursor: pointer;
        }}
        .btn-primary {{ background: var(--primary); color: #090e1a; }}
        .btn-secondary {{ background: var(--surface-2); color: #fff; border: 1px solid var(--border); }}
        .btn-green {{ background: var(--green); color: #042f2e; }}
        .actions-sub {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .btn-chip {{
            background: transparent; color: var(--muted); border: 1px solid var(--border);
            border-radius: 8px; padding: 6px 10px; font-size: 0.74rem; font-weight: 600; cursor: pointer;
        }}
        .btn-chip.on-applied {{ background: rgba(16,185,129,0.2); color: #34d399; border-color: var(--green); }}
        .btn-chip.on-saved {{ background: rgba(245,158,11,0.2); color: #fbbf24; border-color: var(--amber); }}
        .pitch-box {{ margin-top: 10px; }}
        .pitch-box summary {{ color: var(--primary); font-size: 0.8rem; font-weight: 600; cursor: pointer; }}
        pre {{
            background: #050811; border: 1px solid var(--border); border-radius: 8px; padding: 10px;
            font-size: 0.77rem; line-height: 1.45; color: #e2e8f0; white-space: pre-wrap; margin-top: 6px;
        }}
        .empty {{ text-align: center; padding: 36px 12px; color: var(--muted); display: none; }}
        .toast {{
            position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
            background: var(--green); color: #042f2e; font-weight: 800; font-size: 0.84rem;
            padding: 10px 20px; border-radius: 999px; display: none; z-index: 9999;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="top-row">
                <h1>Global Apply Hub</h1>
                <div class="top-actions">
                    {scan_button}
                    <span class="count-pill" id="countBadge">{len(opportunities)} Wide Roles</span>
                </div>
            </div>
            <p class="subline">Updated {html.escape(timestamp)} UTC &bull; Support, QA, Legal-Tech, Ops, Automation &amp; Entry Remote &bull; Zero Paywalls</p>
            {smtp_banner}

            <div class="autofill-box">
                <span><strong>1-Click Form Auto-Filler:</strong> Drag button to Chrome/Edge bar (or copy for iPhone bookmark):</span>
                <div style="display:flex;gap:6px;align-items:center;">
                    <a class="bookmarklet-btn" href="{bookmarklet_href}" onclick="event.preventDefault(); showToast('Drag this button to your bookmarks bar!');">Junaid Auto-Fill</a>
                    <button type="button" class="qchip" onclick="copyAutoFill()">Copy Auto-Fill</button>
                </div>
            </div>

            <div class="quick-bar">
                <button type="button" class="qchip" onclick="copyProf('name')">Copy Name</button>
                <button type="button" class="qchip" onclick="copyProf('email')">Copy Email</button>
                <button type="button" class="qchip" onclick="copyProf('phone')">Copy Phone</button>
                <button type="button" class="qchip" onclick="copyProf('linkedin')">LinkedIn</button>
                <button type="button" class="qchip" onclick="copyProf('github')">GitHub</button>
                <button type="button" class="qchip" onclick="copyProf('portfolio')">Portfolio</button>
                <button type="button" class="qchip" onclick="copyProf('workflow_pro')">WorkFlow Pro</button>
            </div>

            <div class="controls">
                <input type="text" id="searchInput" class="search-box" placeholder="Search support, QA, legal, python, company..." oninput="renderList()">
                <select id="trackSelect" class="select-box" onchange="renderList()">
                    <option value="">All Career Tracks</option>
                    {track_options}
                </select>
            </div>

            <div class="tabs">
                <button type="button" class="tab-btn active" onclick="setTab('todo', this)">To Apply</button>
                <button type="button" class="tab-btn" onclick="setTab('email', this)">Direct Email</button>
                <button type="button" class="tab-btn" onclick="setTab('world', this)">Worldwide</button>
                <button type="button" class="tab-btn" onclick="setTab('saved', this)">Saved</button>
                <button type="button" class="tab-btn" onclick="setTab('applied', this)">Applied</button>
            </div>
        </header>

        <main id="cardsList">
            {"".join(cards)}
        </main>
        <div id="emptyState" class="empty">No roles match this filter. Try switching tracks or tabs.</div>
    </div>

    <div id="toast" class="toast">Done!</div>
    <script id="hub-data" type="application/json">{json_blob}</script>
    <script>
        const HUB = JSON.parse(document.getElementById('hub-data').textContent);
        const LOCAL_KEY = 'global_apply_hub_states_v1';
        let currentTab = 'todo';
        let states = Object.assign({{}}, HUB.initial_states || {{}}, loadLocal());

        function loadLocal() {{
            try {{ return JSON.parse(localStorage.getItem(LOCAL_KEY) || '{{}}'); }}
            catch (_) {{ return {{}}; }}
        }}

        function saveLocal() {{
            try {{ localStorage.setItem(LOCAL_KEY, JSON.stringify(states)); }} catch (_) {{}}
        }}

        function showToast(msg) {{
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.style.display = 'block';
            clearTimeout(window._t);
            window._t = setTimeout(() => {{ t.style.display = 'none'; }}, 2300);
        }}

        function copyRaw(text, label) {{
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(text).then(() => showToast(label));
            }} else {{
                const ta = document.createElement('textarea');
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                showToast(label);
            }}
        }}

        function copyProf(k) {{
            if (HUB.profile[k]) copyRaw(HUB.profile[k], 'Copied ' + k + '!');
        }}

        function copyAutoFill() {{
            if (HUB.bookmarklet) copyRaw(HUB.bookmarklet, 'Auto-Fill code copied for Safari bookmark!');
        }}

        function copyPitch(id, mode) {{
            const item = HUB.pitches[id];
            if (!item) return;
            copyRaw(mode === 'short' ? item.short_pitch : item.cover_note, mode === 'short' ? 'Short pitch copied!' : 'Cover note copied!');
        }}

        async function toggleJob(id, act) {{
            const cur = states[id] || {{}};
            const nextVal = !cur[act];
            cur[act] = nextVal;
            if (act === 'applied' && nextVal) cur.hidden = false;
            states[id] = cur;
            saveLocal();
            renderList();

            if (HUB.local_mode) {{
                try {{
                    await fetch('/api/status/' + encodeURIComponent(id), {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ action: act, value: nextVal }})
                    }});
                }} catch (_) {{}}
            }}
        }}

        async function sendDirectEmail(id) {{
            if (!confirm('Send application email with your PDF Resume attached?')) return;
            showToast('Sending email...');
            try {{
                const res = await fetch('/api/send-email/' + encodeURIComponent(id), {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ custom_body: '' }})
                }});
                const data = await res.json();
                if (!res.ok) {{
                    alert(data.detail || 'Email send failed.');
                    return;
                }}
                states[id] = Object.assign(states[id] || {{}}, {{ applied: true, email_sent: true }});
                saveLocal();
                renderList();
                showToast('Sent with PDF Resume!');
            }} catch (err) {{
                alert('Failed to reach local server: ' + err);
            }}
        }}

        async function runLiveScan() {{
            const btn = document.getElementById('scanBtn');
            btn.disabled = true;
            btn.textContent = 'Scanning...';
            try {{
                const res = await fetch('/api/scan', {{ method: 'POST' }});
                if (res.ok) location.reload();
                else alert('Scan failed.');
            }} finally {{
                btn.disabled = false;
                btn.textContent = 'Scan New Jobs';
            }}
        }}

        function setTab(tab, btn) {{
            currentTab = tab;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderList();
        }}

        function renderList() {{
            const q = document.getElementById('searchInput').value.toLowerCase().trim();
            const track = document.getElementById('trackSelect').value;
            const cards = Array.from(document.querySelectorAll('.card'));
            let shown = 0;

            cards.forEach(c => {{
                const id = c.dataset.id;
                const info = states[id] || {{}};
                c.classList.toggle('is-applied', !!info.applied);
                c.classList.toggle('is-saved', !!info.saved);

                const appBtn = c.querySelector('[data-act="applied"]');
                const savBtn = c.querySelector('[data-act="saved"]');
                if (appBtn) {{
                    appBtn.classList.toggle('on-applied', !!info.applied);
                    appBtn.textContent = info.applied ? 'Applied ✓' : 'Applied';
                }}
                if (savBtn) {{
                    savBtn.classList.toggle('on-saved', !!info.saved);
                    savBtn.textContent = info.saved ? 'Saved ★' : 'Save';
                }}

                const matchQ = !q || (c.dataset.search || '').includes(q);
                const matchTrack = !track || c.dataset.track === track;

                let matchTab = true;
                if (currentTab === 'todo') matchTab = !info.hidden && !info.applied;
                else if (currentTab === 'email') matchTab = !info.hidden && !info.applied && c.dataset.email === '1';
                else if (currentTab === 'world') matchTab = !info.hidden && !info.applied && c.dataset.world === '1';
                else if (currentTab === 'saved') matchTab = !!info.saved;
                else if (currentTab === 'applied') matchTab = !!info.applied;

                const visible = matchQ && matchTrack && matchTab;
                c.style.display = visible ? 'block' : 'none';
                if (visible) shown++;
            }});

            document.getElementById('countBadge').textContent = shown + ' Wide Roles';
            document.getElementById('emptyState').style.display = shown === 0 ? 'block' : 'none';
        }}

        renderList();
    </script>
</body>
</html>
"""


def load_cached_opportunities() -> List[Dict[str, Any]]:
    """Load saved opportunities from disk or run an initial scan if empty."""
    if os.path.exists(OPPORTUNITIES_JSON):
        try:
            with open(OPPORTUNITIES_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    return data
        except Exception:
            pass
    return scan_and_save()


def export_static_html(opportunities: List[Dict[str, Any]]) -> str:
    """Write standalone static HTML dashboard into output/index.html."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    html_doc = render_dashboard_html(opportunities, {}, ts, local_mode=False)
    out_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    return out_path


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Serve the interactive local Global Apply Hub UI."""
    opps = load_cached_opportunities()
    log = load_applied_log()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    return render_dashboard_html(opps, log, ts, local_mode=True)


@app.post("/api/scan")
def trigger_scan():
    """Refresh wide opportunities from live sources."""
    opps = scan_and_save()
    export_static_html(opps)
    return {"count": len(opps)}


@app.post("/api/status/{job_id}")
def set_status(job_id: str, payload: StatusToggleRequest):
    """Toggle applied/saved/hidden flags for a job."""
    if payload.action not in ("applied", "saved", "hidden"):
        raise HTTPException(status_code=400, detail="Unsupported status action.")
    entry = update_job_status(job_id, payload.action, payload.value)
    return {"job_id": job_id, "state": entry}


@app.post("/api/send-email/{job_id}")
def send_email_endpoint(job_id: str, payload: SendEmailRequest):
    """Send 1-click application email with staged PDF resume attached."""
    opps = load_cached_opportunities()
    job = next((o for o in opps if str(o["id"]) == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Job listing not found.")
    result = send_application_email(job, payload.custom_body)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


if __name__ == "__main__":
    print("=" * 64)
    print("  Global Apply Hub: Wide Low-Competition Remote Scanner")
    print("=" * 64)
    print(f"Resume staged: {RESUME_PATH} (exists={os.path.exists(RESUME_PATH)})")
    results = scan_and_save()
    out_file = export_static_html(results)
    print(f"Total wide eligible remote roles: {len(results)}")
    print(f"Static dashboard written: {out_file}")

    by_track: Dict[str, int] = {}
    for item in results:
        by_track[item["track"]] = by_track.get(item["track"], 0) + 1
    print("\nBreakdown by Accessible Track:")
    for tr, cnt in sorted(by_track.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {tr}: {cnt}")

    print("\nTop 10 Lowest-Competition / Best-Fit Roles Today:")
    for idx, item in enumerate(results[:10], 1):
        print(f"  {idx}. [{item['track']}] {item['title']} @ {item['company']} ({item['geo_label']})")
        print(f"     -> {item['url']}")
