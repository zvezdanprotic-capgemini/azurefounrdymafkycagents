"""
Eligibility Agent - Determines customer eligibility
"""
from agent_framework import ChatAgent
from agents.utils import create_azure_chat_client, load_prompt
from maf_tools import get_maf_tools_for_agent


class EligibilityAgent:
    """
    Eligibility Agent - Determines customer eligibility.
    
    Required: completed intake and verification, age >= 18, valid location
    Tools: get_customer_history, search_policies
    """
    
    @staticmethod
    async def create() -> ChatAgent:
        """Create the Eligibility agent with MCP tools."""
        tools = await get_maf_tools_for_agent([
            "get_customer_history",
            "search_policies",
        ])
        
        chat_client = create_azure_chat_client()
        instructions = load_prompt("eligibility")
        
        return chat_client.create_agent(
            name="eligibility",
            description="Eligibility Agent - determines customer eligibility",
            instructions=instructions,
            tools=tools,
        )
