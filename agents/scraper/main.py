"""
Prometheus AI — Scraper Agent
Band SDK v1.0.0 — correct API pattern

LLM: AIML API → gpt-4o-mini
Tool: Firecrawl REST API (Native tool to avoid proxy schema errors)
"""

import asyncio
import json
import logging
import os
import requests

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from band import Agent
from band.adapters.langgraph import LangGraphAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("scraper-agent")

SYSTEM_PROMPT = """You are the Scraper Agent for Prometheus AI — an enterprise documentation and compliance specialist.

When @mentioned with a URL, use your scrape_website tool to:
1. Scrape the full page content as clean markdown.
2. Audit the page for enterprise compliance signals: Is there a Privacy Policy? Terms of Service? Security documentation?
3. Check for enterprise support channels, contact information, or SLA commitments.

Always return a JSON report in this format:
{
  "url": "...",
  "scrape_summary": "brief page description",
  "enterprise_signals": {
    "has_privacy_policy": true,
    "has_terms_of_service": true,
    "has_security_docs": false,
    "has_enterprise_support": false
  },
  "compliance_score": 80,
  "issues": ["No clear security documentation found"],
  "notes": "any additional observations"
}

Return ONLY valid JSON. If scraping fails, return a JSON error object explaining why.
"""

@tool
def scrape_website(url: str) -> str:
    """Scrape a website using Firecrawl and return its content in markdown format."""
    firecrawl_key = os.getenv("FIREWALL_API_KEY")
    if not firecrawl_key:
        return "Error: FIREWALL_API_KEY is not set in .env."
    
    logger.info(f"Scraping {url} via Firecrawl REST API...")
    try:
        response = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={
                "Authorization": f"Bearer {firecrawl_key}", 
                "Content-Type": "application/json"
            },
            json={"url": url, "formats": ["markdown"]},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                markdown = data.get("data", {}).get("markdown", "")
                return f"Successfully scraped {url}. Length: {len(markdown)} chars.\n\nContent:\n{markdown[:4000]}... [TRUNCATED]"
            else:
                return f"Firecrawl returned failure: {json.dumps(data)}"
        else:
            return f"Error scraping {url}: HTTP {response.status_code} - {response.text}"
    except Exception as e:
        logger.error(f"Scrape exception: {e}")
        return f"Exception occurred while scraping {url}: {str(e)}"


async def main():
    load_dotenv()
    logger.info("Starting Prometheus AI — Scraper Agent")

    agent_id = os.getenv("BAND_SCRAPER_AGENT_ID")
    api_key = os.getenv("BAND_SCRAPER_API_KEY")
    if not agent_id or not api_key:
        raise ValueError("BAND_SCRAPER_AGENT_ID and BAND_SCRAPER_API_KEY must be set in .env")

    aiml_key = os.getenv("AIML_API_KEY")
    if not aiml_key:
        raise ValueError("AIML_API_KEY not found in .env")

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=aiml_key,
        base_url="https://api.aimlapi.com/v1",
        temperature=0.1,
        max_tokens=8000,
    )

    adapter = LangGraphAdapter(
        llm=llm,
        checkpointer=MemorySaver(),
        custom_section=SYSTEM_PROMPT,
        additional_tools=[scrape_website],
    )

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
    )

    logger.info("✅ Scraper Agent connecting to Band...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
