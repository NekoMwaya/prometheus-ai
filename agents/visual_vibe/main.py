"""
Prometheus AI — Visual Vibe Agent
Band SDK v1.0.0 — correct API pattern

Orchestrator LLM: AIML API → gpt-4o-mini (for tool calling)
Vision LLM: Featherless AI → Qwen/Qwen3-VL-8B-Instruct (inside tools)
Tool: Playwright (screenshot) + Featherless vision
"""

import asyncio
import base64
import json
import logging
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from band import Agent
from band.adapters.langgraph import LangGraphAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("visual-vibe-agent")

SCREENSHOT_DIR = "playwright-screenshots"

SYSTEM_PROMPT = """You are the Visual Vibe Agent for Prometheus AI — a design quality specialist.

When @mentioned with a URL:
1. Call `take_screenshot(url="<url>")` to capture a full-page screenshot.
2. Call `analyse_screenshot_vibe(screenshot_path="<path from step 1>", url="<url>")` to get the design analysis.
3. Return the JSON report from step 2 as your response.

Always use both tools in sequence. Return ONLY the JSON report.
"""

VISION_PROMPT = """You are a professional UI/UX designer and design critic.
Analyse this website screenshot and provide a vibe check report.

Score each dimension 0-10 and return ONLY valid JSON in this exact format:
{
  "design_analysis": {
    "color_consistency": {"score": 8, "findings": "brief observation"},
    "layout_balance": {"score": 7, "findings": "brief observation"},
    "typography": {"score": 9, "findings": "brief observation"},
    "button_link_visibility": {"score": 6, "findings": "brief observation"},
    "overall_modernity": {"score": 8, "findings": "brief observation"}
  },
  "visual_vibe_score": 8,
  "vibe_summary": "2-3 sentence overall summary",
  "issues": ["specific issue 1", "specific issue 2"],
  "strengths": ["specific strength 1"],
  "recommendations": ["actionable fix 1", "actionable fix 2"]
}"""


@tool
async def take_screenshot(url: str) -> str:
    """Take a full-page screenshot of the given URL using Playwright. Returns the file path to the saved PNG."""
    try:
        from playwright.async_api import async_playwright

        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        safe_name = url.replace("https://", "").replace("http://", "").replace("/", "_").replace(".", "-")
        screenshot_path = os.path.join(SCREENSHOT_DIR, f"{safe_name[:60]}.png")

        logger.info("Taking screenshot of: %s", url)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)

            await page.screenshot(path=screenshot_path, full_page=True)
            await browser.close()

        logger.info("Screenshot saved: %s", screenshot_path)
        return screenshot_path

    except ImportError:
        return "ERROR: Playwright not installed. Run: py -3 -m playwright install chromium"
    except Exception as e:
        logger.error("Screenshot failed: %s", e)
        return f"ERROR: Could not screenshot {url}. Reason: {e}"


@tool
def analyse_screenshot_vibe(screenshot_path: str, url: str) -> str:
    """
    Analyse a screenshot for design quality and vibe using a Featherless vision LLM.
    Returns a JSON string with the vibe analysis and score.
    """
    if screenshot_path.startswith("ERROR") or not os.path.exists(screenshot_path):
        return json.dumps({
            "url": url, "screenshot_taken": False,
            "error": screenshot_path, "visual_vibe_score": 0,
        })

    with open(screenshot_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    featherless_key = os.getenv("FEATHERLESS_API_KEY")
    if not featherless_key:
        return json.dumps({"error": "FEATHERLESS_API_KEY not set", "visual_vibe_score": 0})

    vision_llm = ChatOpenAI(
        model="Qwen/Qwen3-VL-8B-Instruct",
        api_key=featherless_key,
        base_url="https://api.featherless.ai/v1",
        temperature=0.1,
        max_tokens=2000,
    )

    try:
        response = vision_llm.invoke([
            HumanMessage(content=[
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
            ])
        ])

        raw = response.content.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        parsed = json.loads(raw)
        parsed["url"] = url
        parsed["screenshot_taken"] = True
        return json.dumps(parsed, indent=2)

    except json.JSONDecodeError as e:
        return json.dumps({
            "url": url, "screenshot_taken": True,
            "visual_vibe_score": 5,
            "raw_analysis": response.content[:500] if "response" in dir() else "",
            "error": f"JSON parse error: {e}",
        })
    except Exception as e:
        logger.error("Vision analysis failed: %s", e)
        return json.dumps({"url": url, "screenshot_taken": True, "visual_vibe_score": 0, "error": str(e)})


async def main():
    load_dotenv()
    logger.info("Starting Prometheus AI — Visual Vibe Agent")

    agent_id = os.getenv("BAND_VISUAL_VIBE_AGENT_ID")
    api_key = os.getenv("BAND_VISUAL_VIBE_API_KEY")
    if not agent_id or not api_key:
        raise ValueError("BAND_VISUAL_VIBE_AGENT_ID and BAND_VISUAL_VIBE_API_KEY must be set in .env")

    aiml_key = os.getenv("AIML_API_KEY")
    if not aiml_key:
        raise ValueError("AIML_API_KEY not found in .env")

    # Orchestrator LLM: uses AIML API for tool-calling coordination
    # Vision analysis inside tools uses Featherless AI directly
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=aiml_key,
        base_url="https://api.aimlapi.com/v1",
        temperature=0.1,
        max_tokens=4000,
    )
    logger.info("Orchestrator: gpt-4o-mini via AIML | Vision: Qwen2.5-VL via Featherless")

    try:
        from playwright.async_api import async_playwright
        logger.info("Playwright ✅")
    except ImportError:
        logger.warning("⚠️  Playwright missing — run: py -3 -m playwright install chromium")

    adapter = LangGraphAdapter(
        llm=llm,
        checkpointer=MemorySaver(),
        custom_section=SYSTEM_PROMPT,
        additional_tools=[take_screenshot, analyse_screenshot_vibe],
    )

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
    )

    logger.info("✅ Visual Vibe Agent connecting to Band...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
