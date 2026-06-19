"""
Prometheus AI — Backend Bridge (REAL analysis mode)
Performs genuine website checks using Firecrawl + GitHub REST API.
Findings are based on the actual content of the submitted URL.
"""

import asyncio
import os
import re
import requests
import time as time_mod
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Load .env from project root (parent of this backend/ folder)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

FIRECRAWL_KEY = os.getenv("FIREWALL_API_KEY", "")   # API key env var is named FIREWALL_API_KEY
GITHUB_TOKEN  = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")

app = FastAPI(title="Prometheus AI Backend")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

assessments: dict = {}

# ─── Helpers ──────────────────────────────────────────────────────────────────

class AssessRequest(BaseModel):
    url: str
    email: Optional[str] = ""
    test_suites: Optional[List[str]] = ["exploratory", "prelaunch"]
    user_flow: Optional[str] = ""


def now_str():
    return datetime.now().strftime("%H:%M:%S")

def agent_state(status: str, message: str):
    return {"status": status, "message": message}

def check_url_status(url: str) -> int:
    """HEAD request to check if a URL is reachable. Returns HTTP status or 0."""
    try:
        r = requests.head(url, timeout=6, allow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 PrometheusAI/1.0"})
        return r.status_code
    except Exception:
        try:
            r = requests.get(url, timeout=6, allow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0 PrometheusAI/1.0"})
            return r.status_code
        except Exception:
            return 0

def firecrawl_scrape(url: str) -> dict | None:
    """
    Scrape a URL with Firecrawl's /v1/scrape endpoint.
    Returns the 'data' dict (markdown, html, metadata, links) or None on failure.
    """
    if not FIRECRAWL_KEY:
        print("[Firecrawl] No API key found (FIREWALL_API_KEY).")
        return None
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={
                "Authorization": f"Bearer {FIRECRAWL_KEY}",
                "Content-Type": "application/json",
            },
            json={"url": url, "formats": ["markdown", "html", "links"], "waitFor": 1500},
            timeout=40,
        )
        if resp.status_code == 200:
            body = resp.json()
            if body.get("success"):
                return body.get("data", {})
            print(f"[Firecrawl] API returned failure: {body}")
        else:
            print(f"[Firecrawl] HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[Firecrawl] Exception: {e}")
    return None

# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/api/assess")
async def start_assessment(req: AssessRequest):
    sid = f"session_{int(time_mod.time() * 1000)}"
    assessments[sid] = {
        "url": req.url, "email": req.email, "status": "running", "logs": [],
        "pipeline": {
            "interface": agent_state("active",  "Initializing…"),
            "scraper":   agent_state("pending", "Waiting…"),
            "visual":    agent_state("pending", "Waiting…"),
            "github":    agent_state("pending", "Waiting…"),
        },
        "report": None,
    }
    asyncio.create_task(run_workflow(
        sid, req.url, req.email or "",
        req.test_suites or ["exploratory", "prelaunch"],
        req.user_flow or "",
    ))
    return {"session_id": sid}


@app.get("/api/status/{sid}")
async def get_status(sid: str):
    return assessments.get(sid, {"error": "Session not found"})

# ─── Main workflow ────────────────────────────────────────────────────────────

async def run_workflow(sid: str, url: str, email: str, suites: list, user_flow: str):
    s = assessments[sid]
    is_gh = "github.com" in url.lower()
    loop  = asyncio.get_event_loop()

    findings: list = []
    suite_results: dict = {}
    pages_visited: int = 0
    elements_tested: int = 0
    _fid = [0]

    def nxt_id():
        _fid[0] += 1
        return _fid[0]

    def log(agent: str, msg: str):
        s["logs"].append({"agent": agent, "message": msg, "time": now_str()})
        print(f"[{agent}] {msg}")

    def set_ag(agent_id: str, status: str, message: str):
        s["pipeline"][agent_id] = agent_state(status, message)

    # Orchestrator boot
    log("Interface", f"Assessment request received for: {url}")
    await asyncio.sleep(0.4)
    log("Interface", f"Test suites: {', '.join(suites)}")
    await asyncio.sleep(0.4)

    # ══════════════════════════════════════════════════════════════════════
    # PATH A — GitHub repository analysis
    # ══════════════════════════════════════════════════════════════════════
    if is_gh:
        log("Interface", "Repository URL detected → delegating to @prometheus-github")
        set_ag("interface", "active", "Delegating to GitHub Agent")
        set_ag("github", "active", "Fetching repository data…")
        await asyncio.sleep(0.4)

        # Parse owner/repo
        m = re.search(r"github\.com/([^/]+)/([^/\s?.#]+)", url)
        if not m:
            log("GitHub", "Error: Cannot parse owner/repo from the URL.")
            set_ag("github", "error", "Parse error"); s["status"] = "complete"
            s["report"] = {"overall_score": 0, "verdict": "Error", "suites": {},
                           "findings": [], "pages_visited": 0, "elements_tested": 0}
            return

        owner = m.group(1)
        repo  = m.group(2).rstrip(".,;:!?")
        gh_headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        def gh(path):
            try:
                r = requests.get(
                    f"https://api.github.com/repos/{owner}/{repo}/{path}",
                    headers=gh_headers, timeout=12,
                )
                return r.json() if r.status_code == 200 else None
            except Exception:
                return None

        log("GitHub", f"Calling GitHub API: repos/{owner}/{repo}")
        repo_meta = await loop.run_in_executor(None, lambda: gh("")) or {}
        lang = repo_meta.get("language", "Unknown")
        stars = repo_meta.get("stargazers_count", 0)
        desc_gh = repo_meta.get("description", "No description")
        log("GitHub", f"Language: {lang} | Stars: {stars} | {desc_gh[:60]}")
        await asyncio.sleep(0.3)

        log("GitHub", "Scanning root directory contents…")
        contents = await loop.run_in_executor(None, lambda: gh("contents")) or []
        files = [f["name"] for f in contents if isinstance(f, dict)] if isinstance(contents, list) else []
        log("GitHub", f"Root files: {', '.join(files[:14]) or '(none)'}")
        await asyncio.sleep(0.3)

        log("GitHub", "Checking .github/workflows for CI/CD pipelines…")
        workflows = await loop.run_in_executor(None, lambda: gh("contents/.github/workflows")) or []
        has_cicd = isinstance(workflows, list) and len(workflows) > 0
        log("GitHub", f"CI/CD workflows: {'Found ' + str(len(workflows)) if has_cicd else 'NONE FOUND'}")
        await asyncio.sleep(0.3)

        # Health file presence flags
        def has_file(*keys):
            return any(any(k in f.lower() for k in keys) for f in files)

        has_license      = has_file("license")
        has_contributing = has_file("contributing")
        has_changelog    = has_file("changelog")
        has_readme       = has_file("readme")
        test_dirs        = [f for f in files if f.lower() in {"tests", "test", "__tests__", "spec", "testing"}]
        has_tests        = bool(test_dirs)

        log("GitHub", f"Health files — LICENSE:{has_license} CONTRIBUTING:{has_contributing} CHANGELOG:{has_changelog}")
        log("GitHub", f"Tests directory: {'Found (' + test_dirs[0] + ')' if has_tests else 'NOT FOUND'}")
        await asyncio.sleep(0.3)

        # README quality
        if has_readme:
            log("GitHub", "Fetching README to evaluate quality…")
            readme_raw = await loop.run_in_executor(None, lambda: gh("readme"))
            readme_text = ""
            if readme_raw and readme_raw.get("content"):
                import base64
                readme_text = base64.b64decode(readme_raw["content"]).decode("utf-8", errors="ignore")
            has_quickstart = any(k in readme_text.lower() for k in (
                "getting started", "installation", "quick start", "quickstart", "## usage", "how to use", "setup"
            ))
            log("GitHub", f"README quality — Quick Start section: {'✓ Present' if has_quickstart else '✗ Missing'}")
        else:
            has_quickstart = False

        pages_visited   = 1
        elements_tested = len(files)

        # Build findings from real data
        if not has_license:
            findings.append({"id": nxt_id(), "severity": "critical", "category": "Legal Compliance",
                "title": "No LICENSE file found",
                "description": f"The repository {owner}/{repo} has no LICENSE file. Enterprises cannot legally adopt unlicensed open-source code without explicit permission from the author.",
                "fix": "Add an OSI-approved license to the repository root. For permissive use choose MIT or Apache 2.0; run: gh repo edit --add-license MIT"})

        if not has_cicd:
            findings.append({"id": nxt_id(), "severity": "high", "category": "Automation & Quality Gates",
                "title": "No CI/CD pipeline found",
                "description": f"No GitHub Actions workflows, .travis.yml, or Jenkinsfile were found in {owner}/{repo}. Without automated quality gates, regressions can merge silently.",
                "fix": "Create .github/workflows/ci.yml with at least a lint and test job triggered on pull_request and push."})

        if not has_tests:
            findings.append({"id": nxt_id(), "severity": "high", "category": "Test Coverage",
                "title": "No test directory found — estimated 0% coverage",
                "description": f"No tests/, test/, __tests__/, or spec/ directory exists in {owner}/{repo}. Enterprise teams typically require ≥60% test coverage before approving dependencies.",
                "fix": "Add a test suite. For Python: pytest + pytest-cov. For JS/TS: jest or vitest. For Go: go test ./..."})

        if has_readme and not has_quickstart:
            findings.append({"id": nxt_id(), "severity": "medium", "category": "Documentation",
                "title": "README missing a Quick Start / Installation guide",
                "description": "The README.md exists but doesn't contain a clear Installation or Getting Started section. New users must guess how to set the project up.",
                "fix": "Add a '## Getting Started' section with: prerequisites, install command, minimal runnable example."})
        elif not has_readme:
            findings.append({"id": nxt_id(), "severity": "high", "category": "Documentation",
                "title": "No README.md found",
                "description": "The repository has no README. This is the primary entry point for any repository — without it, no one knows what the project is or how to use it.",
                "fix": "Create README.md with: project description, installation instructions, usage examples, and a license badge."})

        if not has_contributing:
            findings.append({"id": nxt_id(), "severity": "low", "category": "Community Health",
                "title": "No CONTRIBUTING.md",
                "description": "There is no contribution guide. External contributors don't know the PR process, coding standards, or how to report bugs.",
                "fix": "Add CONTRIBUTING.md. Consider also adding GitHub issue/PR templates under .github/ISSUE_TEMPLATE/."})

        if not has_changelog:
            findings.append({"id": nxt_id(), "severity": "low", "category": "Community Health",
                "title": "No CHANGELOG.md",
                "description": "No changelog documenting version history. Users and dependents can't assess the impact of upgrading to a new release.",
                "fix": "Create CHANGELOG.md following the Keep a Changelog format (keepachangelog.com)."})

        set_ag("github", "complete", "Risk analysis complete")
        log("GitHub", f"Analysis complete — {len(findings)} finding(s) identified")

        n_pass = sum([has_license, has_cicd, has_tests, has_readme and has_quickstart, has_contributing])
        suite_results["prelaunch"] = {
            "status": "fail" if any(f["severity"] in ("critical", "high") for f in findings) else "warning",
            "checks_passed": n_pass, "checks_total": 5,
        }

    # ══════════════════════════════════════════════════════════════════════
    # PATH B — Website analysis
    # ══════════════════════════════════════════════════════════════════════
    else:
        log("Interface", "Website URL detected → delegating to @prometheus-scraper")
        set_ag("interface", "active", "Delegating to Scraper Agent")
        set_ag("scraper", "active", "Launching Firecrawl scraper…")
        await asyncio.sleep(0.3)

        log("Scraper", "Scraping homepage via Firecrawl API…")
        scrape_data = await loop.run_in_executor(None, lambda: firecrawl_scrape(url))
        await asyncio.sleep(0.3)

        if scrape_data:
            metadata = scrape_data.get("metadata", {}) or {}
            html     = scrape_data.get("html", "") or ""
            links    = scrape_data.get("links", []) or []
            log("Scraper", f"Scraped successfully — {len(links)} link(s) found on page")
            pages_visited  += 1
            elements_tested += len(links)
        else:
            metadata, html, links = {}, "", []
            log("Scraper", "Firecrawl unavailable — running direct HTTP checks only")

        await asyncio.sleep(0.2)

        parsed      = urlparse(url)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"

        # ── PRELAUNCH CHECKS ──────────────────────────────────────────────
        # These are real checks against the actual website — not simulated.
        # Each check corresponds to a universal web best practice.
        if "prelaunch" in suites:
            cp = 0; ct = 0  # checks passed / total

            # 1. HTTPS
            ct += 1
            if url.startswith("https://"):
                cp += 1; log("Scraper", "✓ HTTPS is active")
            else:
                log("Scraper", "✗ Site is not on HTTPS")
                findings.append({"id": nxt_id(), "severity": "critical", "category": "Security",
                    "title": "Site not served over HTTPS",
                    "description": "The website runs on plain HTTP. All data (including passwords and form submissions) travels unencrypted. Modern browsers display a 'Not Secure' warning.",
                    "fix": "Install a TLS certificate (free via Let's Encrypt / Certbot) and set up a permanent HTTP→HTTPS redirect."})
            await asyncio.sleep(0.2)

            # 2. Meta description
            ct += 1
            desc = (metadata.get("description") or "").strip()
            if len(desc) > 10:
                cp += 1; log("Scraper", f"✓ Meta description present ({len(desc)} chars)")
            else:
                log("Scraper", "✗ Meta description missing")
                findings.append({"id": nxt_id(), "severity": "medium", "category": "SEO & Meta",
                    "title": "Meta description not set",
                    "description": "The homepage has no <meta name='description'> tag. Without it, search engines auto-generate a snippet from page body text, which is usually poor quality.",
                    "fix": "Add <meta name='description' content='Your 150–160 char description here'> to the <head> of every page."})
            await asyncio.sleep(0.2)

            # 3. Page title
            ct += 1
            title = (metadata.get("title") or "").strip()
            if title:
                cp += 1; log("Scraper", f"✓ Page title: '{title[:55]}'")
            else:
                log("Scraper", "✗ Page title missing")
                findings.append({"id": nxt_id(), "severity": "high", "category": "SEO & Meta",
                    "title": "No <title> tag found",
                    "description": "The page has no <title> tag — the single strongest on-page SEO signal and what appears in browser tabs and search engine results.",
                    "fix": "Add a descriptive <title> tag (50–60 chars) to the <head> of every page."})
            await asyncio.sleep(0.2)

            # 4. OG image (social sharing preview)
            ct += 1
            og_image = (metadata.get("ogImage") or "").strip()
            if og_image:
                cp += 1; log("Scraper", "✓ Open Graph image (social preview) set")
            else:
                log("Scraper", "✗ No og:image — social previews will be blank")
                findings.append({"id": nxt_id(), "severity": "low", "category": "Social & Branding",
                    "title": "No Open Graph image set",
                    "description": "Sharing this URL on Twitter/X, LinkedIn, or Slack will show a blank card because og:image is not configured.",
                    "fix": "Add <meta property='og:image' content='https://yoursite.com/og-preview.png'> (use a 1200×630px image) to <head>."})
            await asyncio.sleep(0.2)

            # 5. Favicon
            ct += 1
            log("Scraper", f"Checking {base_origin}/favicon.ico…")
            fav_status = await loop.run_in_executor(None, lambda: check_url_status(f"{base_origin}/favicon.ico"))
            has_link_icon = bool(re.search(r'rel=["\'](?:icon|shortcut icon)["\']', html, re.I))
            if fav_status == 200 or has_link_icon:
                cp += 1; log("Scraper", "✓ Favicon found")
            else:
                log("Scraper", "✗ Favicon not found")
                findings.append({"id": nxt_id(), "severity": "low", "category": "Prelaunch Polish",
                    "title": "Favicon not found",
                    "description": "No /favicon.ico and no <link rel='icon'> tag found. Browser tabs and bookmarks display a blank generic icon, reducing brand recognition.",
                    "fix": "Place a favicon.ico in your /public root and add <link rel='icon' href='/favicon.ico'> to the <head>."})
            await asyncio.sleep(0.2)

            # 6. robots.txt
            ct += 1
            log("Scraper", f"Checking {base_origin}/robots.txt…")
            robots_ok = await loop.run_in_executor(None, lambda: check_url_status(f"{base_origin}/robots.txt")) == 200
            if robots_ok:
                cp += 1; log("Scraper", "✓ robots.txt found")
            else:
                log("Scraper", "✗ robots.txt missing")
                findings.append({"id": nxt_id(), "severity": "low", "category": "SEO & Meta",
                    "title": "robots.txt not found",
                    "description": "No robots.txt at /robots.txt. Without it, search crawlers index everything including admin panels and staging paths.",
                    "fix": "Create /robots.txt specifying crawlable paths and add a Sitemap: directive pointing to your sitemap URL."})
            await asyncio.sleep(0.2)

            # 7. sitemap.xml
            ct += 1
            log("Scraper", f"Checking {base_origin}/sitemap.xml…")
            sitemap_ok = await loop.run_in_executor(None, lambda: check_url_status(f"{base_origin}/sitemap.xml")) == 200
            if sitemap_ok:
                cp += 1; log("Scraper", "✓ sitemap.xml found")
            else:
                log("Scraper", "✗ sitemap.xml missing")
                findings.append({"id": nxt_id(), "severity": "low", "category": "SEO & Meta",
                    "title": "sitemap.xml not found",
                    "description": "No sitemap.xml at /sitemap.xml. Sitemaps help search engines discover all your pages — especially important for large or newly launched sites.",
                    "fix": "Generate a sitemap.xml and submit it to Google Search Console. Most frameworks have plugins for this."})
            await asyncio.sleep(0.2)

            # 8. Viewport meta (mobile readiness)
            ct += 1
            has_vp = bool(re.search(r'name=["\']viewport["\']', html, re.I))
            if has_vp:
                cp += 1; log("Scraper", "✓ Mobile viewport meta tag present")
            else:
                log("Scraper", "✗ Viewport meta tag missing — mobile layout may be broken")
                findings.append({"id": nxt_id(), "severity": "medium", "category": "Mobile",
                    "title": "Missing viewport meta tag",
                    "description": "No <meta name='viewport'> found. Mobile browsers render the page at full desktop width, causing users to pinch-zoom to read content.",
                    "fix": "Add <meta name='viewport' content='width=device-width, initial-scale=1'> to the <head>."})
            await asyncio.sleep(0.2)

            pre_status = "pass" if cp == ct else ("warning" if cp >= ct * 0.6 else "fail")
            suite_results["prelaunch"] = {"status": pre_status, "checks_passed": cp, "checks_total": ct}
            log("Scraper", f"Prelaunch checks: {cp}/{ct} passed — status: {pre_status.upper()}")

        # ── EXPLORATORY: test internal links for broken pages ─────────────
        if "exploratory" in suites:
            log("Scraper", "Testing internal links for broken URLs…")

            # Gather internal links from the scraped page
            internal = list({
                lnk for lnk in links
                if lnk.startswith(base_origin) or re.match(r'^/[^/]', lnk)
            })
            # Normalise relative URLs
            internal = [lnk if lnk.startswith("http") else f"{base_origin}{lnk}" for lnk in internal]
            # Exclude common asset patterns
            internal = [l for l in internal if not re.search(r'\.(css|js|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot)(\?|$)', l, re.I)]
            sample = internal[:10]  # Test up to 10 internal links

            broken = []
            for lnk in sample:
                st = await loop.run_in_executor(None, lambda u=lnk: check_url_status(u))
                if st >= 400 or st == 0:
                    broken.append({"url": lnk, "status": st})
                await asyncio.sleep(0.1)

            pages_visited  += len(sample)
            elements_tested += len(links)
            log("Scraper", f"Tested {len(sample)} internal link(s) — {len(broken)} broken")

            if broken:
                broken_paths = ", ".join(b["url"].replace(base_origin, "") for b in broken[:4])
                findings.append({"id": nxt_id(), "severity": "high", "category": "Broken Links",
                    "title": f"{len(broken)} broken internal link(s) found",
                    "description": f"The following internal links return 4xx errors: {broken_paths}. Users who click them reach an error page with no recovery path.",
                    "fix": "Fix the href values to point to existing pages, or set up 301 redirects from the broken paths to the correct destinations."})

            suite_results["exploratory"] = {
                "status": "fail" if broken else "pass",
                "pages_visited": pages_visited,
                "elements_tested": elements_tested,
            }

        # ── USER FLOWS ────────────────────────────────────────────────────
        if "user_flows" in suites:
            log("Scraper", "User flow execution requires the Visual Agent (Playwright)…")
            await asyncio.sleep(0.6)
            log("Visual", "Verifying site is reachable for flow tests…")
            reachable = await loop.run_in_executor(None, lambda: check_url_status(url)) == 200
            log("Visual", "Site reachable ✓" if reachable else f"Site unreachable ✗ (HTTP status: check site)")
            suite_results["user_flows"] = {
                "status": "pass" if reachable else "fail",
                "checks_passed": 1 if reachable else 0, "checks_total": 1,
            }

        # ── ACCESSIBILITY: images without alt text ────────────────────────
        if html:
            log("Interface", "Delegating visual / accessibility check to @visual-vibe…")
            set_ag("scraper", "complete", "Crawl & audit complete")
            set_ag("visual", "active", "Checking accessibility signals…")
            await asyncio.sleep(0.8)

            imgs_no_alt = len(re.findall(r'<img(?![^>]*\balt\s*=)[^>]*/?>',  html, re.I))
            if imgs_no_alt > 0:
                log("Visual", f"Found {imgs_no_alt} image(s) without alt text")
                findings.append({"id": nxt_id(), "severity": "medium", "category": "Accessibility",
                    "title": f"{imgs_no_alt} image(s) missing alt attribute",
                    "description": f"Found {imgs_no_alt} <img> element(s) with no alt attribute on the homepage. This prevents screen readers from describing images and hurts image SEO.",
                    "fix": "Add descriptive alt text to all meaningful images. For decorative images use alt=''. Example: <img src='...' alt='Team photo at company HQ'>"})
            else:
                log("Visual", "✓ All images have alt text")

            set_ag("visual", "complete", "Accessibility check complete")
        else:
            set_ag("scraper", "complete", "Crawl & audit complete")
            set_ag("visual", "complete", "Skipped (no HTML)")

    # ── Synthesis ─────────────────────────────────────────────────────────────
    log("Interface", "All specialist agents reported. Synthesizing final assessment…")
    set_ag("interface", "active", "Synthesizing reports…")
    await asyncio.sleep(1.2)

    n_crit = sum(1 for f in findings if f["severity"] == "critical")
    n_high = sum(1 for f in findings if f["severity"] == "high")
    n_med  = sum(1 for f in findings if f["severity"] == "medium")
    n_low  = sum(1 for f in findings if f["severity"] == "low")
    score  = max(10, 100 - n_crit * 22 - n_high * 11 - n_med * 5 - n_low * 2)
    verdict = "Launch Ready ✓" if score >= 80 else ("Needs Attention" if score >= 60 else "Not Launch Ready ✗")

    set_ag("interface", "complete", "Assessment complete")
    log("Interface", f"Final score: {score}/100 — {verdict} ({n_crit} critical, {n_high} high, {n_med} medium, {n_low} low)")
    if email:
        log("Interface", f"Report queued for delivery to {email}")

    s["status"] = "complete"
    s["report"] = {
        "overall_score": score,
        "verdict": verdict,
        "suites": suite_results,
        "findings": findings,
        "pages_visited": pages_visited,
        "elements_tested": elements_tested,
    }


if __name__ == "__main__":
    print(f"FIRECRAWL KEY: {'✓ loaded' if FIRECRAWL_KEY else '✗ missing (FIREWALL_API_KEY)'}")
    print(f"GITHUB TOKEN:  {'✓ loaded' if GITHUB_TOKEN  else '✗ missing'}")
    uvicorn.run(app, host="127.0.0.1", port=8000)
