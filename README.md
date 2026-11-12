# Global Apply Hub

Wide-spectrum, lower-competition remote job scanner and 1-click application helper. Designed as a standalone companion project without modifying `client-radar`.

## Features
- **5 Accessible Career Tracks:** Tech Support & Solutions, Legal-Tech & Compliance (leveraging BS CS + LLB), QA & Software Testing, Data/Research/Operations, and Junior/Entry & Automation.
- **Zero-Paywall, Worldwide/EMEA/APAC Eligible:** Automatically excludes US-only, hybrid, on-site, paywalled portals, and non-English-required postings.
- **1-Click Bookmarklet Auto-Filler:** Fills Name, Email, Phone, Location, LinkedIn, GitHub, and Portfolio across React/Ashby/Greenhouse ATS forms in a single click.
- **1-Click PDF Resume Email Sender:** Attaches `assets/Muhammad_Junaid_Warraich_Resume.pdf` and prevents duplicate sends via `data/applied_log.json`.

## Quick Start
1. Double-click `run_hub.bat` (or run `python -m uvicorn app:app --port 8085`).
2. Open `http://127.0.0.1:8085` in Chrome/Edge.
3. Drag the **Junaid Auto-Fill** button onto your Bookmarks Bar to auto-fill web forms in 1 second.
4. *(Optional)* Copy `.env.example` to `.env` with a Gmail App Password to send direct-email applications directly from the dashboard.
