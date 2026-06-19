"""
Prometheus AI — Interface Agent (Orchestrator)
Band SDK v1.0.0 — correct API pattern

LLM: AIML API → gpt-4o-mini
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from band import Agent
from band.adapters.langgraph import LangGraphAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("interface-agent")

SYSTEM_PROMPT = """You are the Interface Agent — the orchestrator for Prometheus AI, an "Automated Open-Source Risk & Compliance Assessor".

## Your Role
You receive user requests to assess a repository or website for enterprise readiness, security, and risk.
You coordinate specialist agents via @mentions in the Band chat room. You can query them in parallel or sequentially. Synthesise their reports into a comprehensive Enterprise Risk Assessment.

## Specialist Agents Available
1. **@prometheus-github** — Analyses a GitHub repo for code quality, security practices, test coverage, and project maintenance health. Accepts: a GitHub repo URL.
2. **@prometheus-scraper** — Uses Firecrawl to scrape a URL, auditing documentation, finding support links, and assessing compliance. Accepts: a website URL.
3. **@visual-vibe** — Takes a Playwright screenshot and analyses UI/UX quality, accessibility, and professional appearance. Accepts: any URL.

## Workflow
- **GitHub repo assessment** (e.g. `assess github.com/user/repo`): Delegate to @prometheus-github to check code health. You may also delegate to @prometheus-scraper to check its documentation site (if any), and @visual-vibe. 
- **Website assessment** (e.g. `assess https://example.com`): Delegate to @prometheus-scraper and @visual-vibe.

CRITICAL RULES:
1. You can delegate to multiple agents, but DO NOT send the exact same delegation twice.
2. Wait for the agents to reply with their JSON reports.
3. Once you have sufficient data, synthesise it into an Enterprise Risk Report. Do NOT re-delegate once you have the reports.
4. Your final synthesis should be addressed to the original user (e.g. @Tan Kang).

## Delegation Format
- "@prometheus-github Please perform a risk analysis on the GitHub repo at https://github.com/owner/repo focusing on security, CI/CD, and maintenance."
- "@prometheus-scraper Please scrape https://example.com and return an audit of compliance, privacy policies, and enterprise support links."

## Final Report Format
Synthesise into a concise Enterprise Risk Report with:
- Overall Enterprise Readiness Score (0-100)
- Security & Compliance Risks (vulnerabilities, missing licenses)
- Maintenance & Code Health (CI/CD, tests, activity)
- Actionable Mitigation Recommendations
"""


async def main():
    load_dotenv()
    logger.info("Starting Prometheus AI — Interface Agent")

    agent_id = os.getenv("BAND_INTERFACE_AGENT_ID")
    api_key = os.getenv("BAND_INTERFACE_API_KEY")
    if not agent_id or not api_key:
        raise ValueError("BAND_INTERFACE_AGENT_ID and BAND_INTERFACE_API_KEY must be set in .env")

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
    logger.info("LLM: gpt-4o-mini via AIML API")

    # The Interface agent's own ID — used to detect and drop its own messages.
    own_agent_id = agent_id

    class LoopSafeInterfaceAdapter(LangGraphAdapter):
        """
        Custom adapter that prevents the Interface agent from looping by
        dropping messages it sent itself, identified via sender_id.
        """

        async def on_started(self, agent_name: str, agent_description: str) -> None:
            await super().on_started(agent_name, agent_description)
            logger.info(f"Interface agent started as: '{agent_name}' (id={own_agent_id})")

        async def on_message(self, msg, room_id: str, **kwargs):
            sender_type = getattr(msg, "sender_type", "UNKNOWN")
            sender_name = getattr(msg, "sender_name", "UNKNOWN") or ""
            sender_id   = getattr(msg, "sender_id",   "UNKNOWN") or ""
            msg_id = getattr(msg, "id", "?")

            logger.info(
                f"[MSG {msg_id[:8]}] sender_type='{sender_type}' "
                f"sender_name='{sender_name}' sender_id='{sender_id[:12]}...' "
                f"content_preview={repr(msg.content[:80])}"
            )

            # --- LOOP PREVENTION: Drop messages this agent sent itself ---
            # Band delivers ALL room messages to every agent, including the
            # agent's own outgoing messages. Comparing sender_id against our
            # own agent_id is unambiguous (no string-format mismatch risk).
            if sender_id == own_agent_id:
                logger.info(
                    f"[LOOP GUARD] Dropping own message (sender_id matches own agent_id). "
                    f"Interface agent must not respond to itself."
                )
                return  # Silently discard — do NOT call super() or the LLM.

            # All other messages (user requests AND specialist agent reports)
            # are passed to the LLM. The system prompt instructs it not to
            # re-delegate once it has received a report.
            await super().on_message(msg=msg, room_id=room_id, **kwargs)

    adapter = LoopSafeInterfaceAdapter(
        llm=llm,
        checkpointer=MemorySaver(),
        custom_section=SYSTEM_PROMPT,
    )

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
    )

    logger.info("✅ Interface Agent connecting to Band...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())