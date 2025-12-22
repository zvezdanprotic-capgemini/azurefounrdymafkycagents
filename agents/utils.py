"""
Shared utilities for MAF agents
"""
import os
import logging
from pathlib import Path
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

logger = logging.getLogger("kyc.maf_agents")


def create_azure_chat_client() -> AzureOpenAIChatClient:
    """Create Azure OpenAI chat client for MAF agents."""
    try:
        return AzureOpenAIChatClient(
            credential=AzureCliCredential() if not os.getenv("AZURE_OPENAI_API_KEY") else None
        )
    except Exception as e:
        logger.warning(f"Could not create AzureOpenAIChatClient with CLI credential: {e}")
        return AzureOpenAIChatClient()


def load_prompt(agent_name: str) -> str:
    """Load prompt from file."""
    prompt_file = Path(__file__).parent / "prompts" / f"{agent_name}_prompt.txt"
    with open(prompt_file, "r") as f:
        return f.read()
