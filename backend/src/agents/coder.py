"""Coder agent factory using langchain.agents.create_agent."""

from typing import Any, Optional

from langchain import agents
from langchain_core.tools import BaseTool

from src.config.code_language import CodeLanguageType
from src.service.llm import LLMService
from src.prompts.template import format_snippets_for_prompt, get_processed_prompt
from src.tools.execute_code import execute_code
from src.tools.execute_r_code import execute_r_code
from src.tools.s3_operations import read_file_from_s3, list_s3_files
from src.tools.file_operations import list_files_by_thread, list_files_by_type


def compose_coder_system_prompt(
    user_id: Optional[str],
    project_snippets: list[dict] | None,
    code_language: CodeLanguageType,
) -> str:
    """Compose the coder's system prompt (base + language modules + snippets).

    Shared between the LangChain coder factory and the SDK-based coder so
    both backends send a byte-identical system prompt for honest A/B
    evaluation. Any future change to prompt composition should happen here
    and flow to both paths automatically.
    """
    s3_user_id = user_id if user_id else "anonymous"
    template_vars = {
        "USER_ID": s3_user_id,
        "PROJECT_SNIPPETS": format_snippets_for_prompt(project_snippets),
    }

    system_prompt = get_processed_prompt("coder", template_vars=template_vars)
    if code_language in ("python", "auto"):
        system_prompt += "\n\n" + get_processed_prompt("coder_python", template_vars=template_vars)
    if code_language in ("r", "auto"):
        system_prompt += "\n\n" + get_processed_prompt("coder_r", template_vars=template_vars)
    return system_prompt


def create_coder_agent(
    tools: list[BaseTool] | None = None,
    user_id: Optional[str] = None,
    project_snippets: list[dict] | None = None,
    code_language: CodeLanguageType = "python",
) -> Any:
    """Create a coder agent with dynamic language support.

    The agent's prompt and tools are composed dynamically based on the
    code_language parameter, following the same context-injection pattern
    as research_mode and database_id.

    Args:
        tools: Optional additional tools to include
        user_id: Optional user ID for constructing S3 paths
        project_snippets: Optional list of snippet dicts to inject into prompt
        code_language: Language preference ("python", "r", or "auto")

    Returns:
        Compiled LangGraph agent for code execution tasks
    """
    llm = LLMService.get_llm_by_agent("coder", temperature=0.7)

    # Build tool list based on language selection
    agent_tools = [
        read_file_from_s3,
        list_s3_files,
        list_files_by_thread,
        list_files_by_type,
    ]
    if code_language in ("python", "auto"):
        agent_tools.append(execute_code)
    if code_language in ("r", "auto"):
        agent_tools.append(execute_r_code)
    if tools:
        agent_tools.extend(tools)

    system_prompt = compose_coder_system_prompt(
        user_id=user_id,
        project_snippets=project_snippets,
        code_language=code_language,
    )

    agent = agents.create_agent(
        model=llm,
        tools=agent_tools,
        system_prompt=system_prompt,
    )

    return agent
