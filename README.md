<div align="center">
  <h1>🔮 Prometheus AI</h1>
  <p><strong>Autonomous browser agents that test your site for launch confidence</strong></p>
  <p>
    Built for the <a href="https://lablab.ai/ai-hackathons/band-of-agents-hackathon">Lablab Band of Agents Hackathon</a>
  </p>
</div>

<br />

Vibe coding has been present and growing year by year, empowering more creators to build software faster than ever. However, beginners who want to push their websites into production often do not fully understand the risks of being exposed to DDoS attacks, cybersecurity vulnerabilities, or catastrophic UX failures. That's why Prometheus AI was built—to thoroughly "vibe check" websites before they are pushed into production. By running autonomous, AI-powered browser agents against your website, Prometheus AI acts as your prelaunch safety net. It scrapes your site to find missing links, missing meta descriptions, bad processing methods, and missing or broken visuals. Just provide your website URL and an email address—our agents will run in the background and deliver an actionable report to your inbox so you can build and ship with confidence.

![Prometheus AI Dashboard Preview](https://github.com/KenjiPcx/Buffalo-AI/raw/main/assets/preview.png)

## Why Prometheus AI?

- **Confidence to launch:** Catch regressions, SEO issues, and rough edges before your users do.
- **No setup required:** Point us at a URL or a GitHub Repository. That’s it.
- **Actionable output:** Clear, prioritized fixes—not just raw logs.

## What Prometheus AI Tests

### 🧭 Exploratory Tests
Our Scraper Agent crawls common layouts and navigation patterns across your site, clicking links, interacting with elements, and validating outcomes to ensure there are no dead-ends or broken links.

### 🔄 User Flow Tests
Powered by our Visual Agent, Prometheus executes custom end-to-end journeys with screenshot evidence to ensure your sign-up, checkout, or onboarding flows are flawless.

### ✅ Prelaunch Checks
A specialized agent runs a definitive 8-point prelaunch checklist:
1. **HTTPS Enforcement**
2. **Meta Descriptions & SEO Tags**
3. **Open Graph Social Previews**
4. **Favicon Presence**
5. **Mobile Viewport Optimization**
6. **Robots.txt Configuration**
7. **Sitemap.xml Availability**
8. **Image Accessibility (Alt tags)**

### 🐙 Enterprise Repository Risk (GitHub)
For open-source and enterprise libraries, Prometheus AI audits your codebase for:
- OSI-approved Licenses
- Continuous Integration & Deployment (CI/CD) pipelines
- Test coverage directories
- High-quality READMEs and `CONTRIBUTING.md` guidelines

---

## 🛠️ Architecture

Prometheus uses a multi-agent orchestration pattern to delegate tasks and synthesize findings.

- **Orchestrator Agent:** Receives the URL, delegates tasks to specialists, and synthesizes the final report.
- **Scraper Agent:** Uses Firecrawl to scrape the DOM, extract links, and audit metadata.
- **Visual Agent:** Analyzes UI layouts and accessibility using vision models.
- **GitHub Agent:** Audits repository health via the GitHub REST API.

The stack includes:
- **Frontend:** React + Vite (Tailwind CSS, Lucide Icons)
- **Backend/Orchestration:** FastAPI (Python)
- **Scraping:** Firecrawl API
- **Repository Analysis:** GitHub REST API

---

## 🚀 Getting Started

### Prerequisites

- Node.js 18+ (for the dashboard)
- Python 3.11+ (for the backend orchestration)
- API Keys for Firecrawl and GitHub

### 1. Clone & Configure

```bash
git clone https://github.com/thenvoi/codeband.git
cd codeband

# Set up your environment variables
cp .env.example .env
```
Ensure your `.env` contains:
```env
FIREWALL_API_KEY="your_firecrawl_api_key_here"
GITHUB_PERSONAL_ACCESS_TOKEN="your_github_pat_here"
```

### 2. Run the Backend (Orchestrator)

The FastAPI backend coordinates the agents and runs the real website/repo analysis.

```bash
# Install Python dependencies
cd backend
pip install -r requirements.txt

# Start the server
python main.py
```

### 3. Run the Dashboard

In a new terminal, launch the premium user interface:

```bash
cd dashboard
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser. Enter a website (e.g., `https://example.com`) or a GitHub repository, and watch the agents work in real time!

---

## 🏆 Hackathon Alignment

This project was built to align perfectly with the **Band of Agents Hackathon**. By pivoting to an **Enterprise Risk & Launch Confidence** platform, it showcases how multi-agent systems can handle complex, multi-step asynchronous tasks (scraping, GitHub analysis, and visual checks) while presenting a deeply engaging, Buffalo AI-inspired user interface.

<div align="center">
  <p>Built with ❤️ by the Prometheus Team</p>
</div>
