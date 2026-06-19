"""
Prometheus AI — GitHub Agent
Band SDK v1.0.0 — correct API pattern

LLM: AIML API → gpt-4o-mini
Tool: Native GitHub REST API (Native tool to avoid proxy schema and MCP errors)
"""

import asyncio
import dataclasses
import logging
import os
import re
import requests
import time

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from band import Agent
from band.adapters.langgraph import LangGraphAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("github-agent")

SYSTEM_PROMPT = """You are the GitHub Agent for Prometheus AI — an Enterprise Risk & Compliance specialist.

When @mentioned with a GitHub repo URL or owner/repo reference, use your analyze_github_repo tool to fetch the repository metadata and directory structure.

Check the following based on the tool's output to assess enterprise readiness:
1. README.md — Does it exist? Does it look professional and well-documented?
2. Tests — Are there test directories (tests/, test/, __tests__/, spec/)? Are there test files? (Crucial for enterprise reliability)
3. CI/CD — Is there .github/workflows/, .travis.yml, Jenkinsfile, or similar? (Crucial for automated quality gates)
4. Project health & compliance files — LICENSE (crucial for legal compliance), CONTRIBUTING.md, CHANGELOG.md, .env.example?

Always return your final report as TEXT in this JSON format:
{
  "repo": "owner/repo-name",
  "language": "primary language",
  "description": "repo description",
  "readme": {"exists": true, "quality": "good/fair/poor", "issues": ["..."]},
  "tests": {"exists": true, "test_directories": ["tests/"], "estimated_coverage": "unknown/low/medium/high"},
  "cicd": {"exists": true, "tools": ["GitHub Actions"]},
  "project_health_files": {"has_license": true, "has_contributing": false, "has_changelog": false, "has_env_example": true},
  "enterprise_risk_score": 70,
  "security_concerns": ["No tests found", "Missing LICENSE file"],
  "strengths": ["Good CI/CD setup"],
  "mitigation_recommendations": ["Add unit tests", "Add a LICENSE to ensure compliance"]
}

CRITICAL: Do NOT use any tools to output your final answer. You must reply directly with the JSON text.
Always start your reply with: @Prometheus Interface
"""

@tool
def analyze_github_repo(repo_url_or_name: str) -> str:
    """Fetch GitHub repository metadata, file tree, and README snippet to analyze repository health."""
    github_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not github_token:
        return "Error: GITHUB_PERSONAL_ACCESS_TOKEN is not set in .env."
    
    # Extract owner/repo
    match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url_or_name)
    if match:
        owner, repo = match.groups()
    else:
        parts = repo_url_or_name.strip("/").split("/")
        if len(parts) >= 2:
            owner, repo = parts[-2], parts[-1]
        else:
            return "Error: Could not parse owner/repo from input."
    
    owner = owner.replace("https:", "").replace("http:", "").strip()
    repo = repo.replace(".git", "").strip().rstrip(".,;:!?")
    
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    logger.info(f"Analyzing GitHub repo: {owner}/{repo}")
    try:
        # 1. Get Repo Details
        resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers, timeout=15)
        if resp.status_code != 200:
            return f"Error fetching repo {owner}/{repo}: HTTP {resp.status_code} - {resp.json().get('message', '')}"
        repo_data = resp.json()
        
        # 2. Get Root Directory Contents
        tree_resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}/contents", headers=headers, timeout=15)
        files = []
        if tree_resp.status_code == 200:
            files = [item['name'] for item in tree_resp.json()]
            
        # 3. Check for .github/workflows
        workflows_resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}/contents/.github/workflows", headers=headers, timeout=15)
        workflows = []
        if workflows_resp.status_code == 200:
            workflows = [item['name'] for item in workflows_resp.json()]
            
        # 4. Fetch README snippet
        readme_resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}/readme", headers=headers, timeout=15)
        readme_snippet = "No README found."
        if readme_resp.status_code == 200:
            import base64
            content_b64 = readme_resp.json().get('content', '')
            if content_b64:
                full_readme = base64.b64decode(content_b64).decode('utf-8', errors='ignore')
                readme_snippet = full_readme[:1000] + "\n... [TRUNCATED]"
        
        report = (
            f"Repository: {owner}/{repo}\n"
            f"Description: {repo_data.get('description', 'None')}\n"
            f"Primary Language: {repo_data.get('language', 'Unknown')}\n"
            f"Stars: {repo_data.get('stargazers_count', 0)}, Forks: {repo_data.get('forks_count', 0)}\n\n"
            f"--- Root Files & Directories ---\n"
            f"{', '.join(files) if files else 'None'}\n\n"
            f"--- CI/CD Workflows (.github/workflows) ---\n"
            f"{', '.join(workflows) if workflows else 'None'}\n\n"
            f"--- README Snippet ---\n"
            f"{readme_snippet}\n"
        )
        return report
        
    except Exception as e:
        logger.error(f"GitHub exception: {e}")
        return f"Exception occurred while analyzing {owner}/{repo}: {str(e)}"


async def main():
    load_dotenv()
    logger.info("Starting Prometheus AI — GitHub Agent")

    agent_id = os.getenv("BAND_GITHUB_AGENT_ID")
    api_key = os.getenv("BAND_GITHUB_API_KEY")
    if not agent_id or not api_key:
        raise ValueError("BAND_GITHUB_AGENT_ID and BAND_GITHUB_API_KEY must be set in .env")

    github_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not github_token:
        raise ValueError(
            "GITHUB_PERSONAL_ACCESS_TOKEN not found in .env. "
            "Create a read-only PAT at https://github.com/settings/tokens"
        )

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

    # The GitHub agent's own ID — used to detect and drop its own outgoing messages.
    own_agent_id = agent_id

    # Cooldown: (room_id, repo_key) → last_processed_timestamp
    # Prevents re-analyzing the same repo in the same room within COOLDOWN_SECONDS.
    COOLDOWN_SECONDS = 60
    _repo_cooldowns: dict[tuple[str, str], float] = {}

    class DirectGitHubAdapter(LangGraphAdapter):

        async def on_started(self, agent_name: str, agent_description: str) -> None:
            await super().on_started(agent_name, agent_description)
            logger.info(f"GitHub agent started as: '{agent_name}' (id={own_agent_id})")

        async def on_message(self, msg, room_id: str, **kwargs):
            sender_type = getattr(msg, "sender_type", "UNKNOWN")
            sender_name = getattr(msg, "sender_name", "UNKNOWN")
            sender_id   = getattr(msg, "sender_id",   "UNKNOWN") or ""
            msg_id = getattr(msg, "id", "?")
            logger.info(
                f"[MSG {msg_id[:8]}] sender_type='{sender_type}' "
                f"sender_name='{sender_name}' sender_id='{sender_id[:12]}...' "
                f"content_preview={repr(msg.content[:80])}"
            )

            # --- LOOP PREVENTION LAYER 1: Drop messages this agent sent itself ---
            # The GitHub agent's own replies come back as room messages.
            # If we processed them, we'd analyze the repo again from our own reply text.
            if sender_id == own_agent_id:
                logger.info(
                    f"[LOOP GUARD] Dropping own message (sender_id matches own agent_id)."
                )
                return  # Do NOT call super() — avoids feeding our own reply back into the LLM.

            content = msg.content

            # --- LOOP PREVENTION LAYER 2: Per-room cooldown per repo ---
            # Even if Layer 1 fails, the same repo won't be re-analyzed within COOLDOWN_SECONDS.
            url_match = re.search(r'github\.com/([^/ \n]+/[^/ \n.,;:!?\n]+)', content)
            if url_match:
                repo_ref = url_match.group(1).rstrip(".,;:!?")
                cooldown_key = (room_id, repo_ref.lower())
                now = time.monotonic()
                last_time = _repo_cooldowns.get(cooldown_key, 0)

                if now - last_time < COOLDOWN_SECONDS:
                    remaining = int(COOLDOWN_SECONDS - (now - last_time))
                    logger.warning(
                        f"[COOLDOWN] Repo '{repo_ref}' was already analyzed in room {room_id[:8]} "
                        f"{int(now - last_time)}s ago. Skipping (cooldown: {remaining}s remaining)."
                    )
                    return

                # Record analysis timestamp before calling tool
                _repo_cooldowns[cooldown_key] = now
                logger.info(f"Intercepted repo ref: {repo_ref}")

                # Call tool directly in Python
                try:
                    tool_result = analyze_github_repo.invoke({"repo_url_or_name": repo_ref})
                except Exception as e:
                    tool_result = f"Error calling tool: {e}"

                # msg is a frozen dataclass — use dataclasses.replace() for a new copy.
                new_content = (
                    content
                    + f"\n\n[SYSTEM: The tool analyze_github_repo returned the following data. "
                    f"Use it to generate the JSON report:]\n{tool_result}"
                )
                msg = dataclasses.replace(msg, content=new_content)

            await super().on_message(msg=msg, room_id=room_id, **kwargs)

    adapter = DirectGitHubAdapter(
        llm=llm,
        checkpointer=MemorySaver(),
        custom_section=SYSTEM_PROMPT,
        additional_tools=[],  # NO TOOLS — bypasses the AIML API streaming bug.
    )

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
    )

    logger.info("✅ GitHub Agent connecting to Band...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
