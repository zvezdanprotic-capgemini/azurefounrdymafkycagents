"""
Compliance Agent - Performs final compliance checks
"""
from agent_framework import ChatAgent
from agents.utils import create_azure_chat_client, load_prompt
from maf_tools import get_maf_tools_for_agent


class ComplianceAgent:
    """
    Compliance Agent - Performs final compliance checks.
    
    Required: source of funds, employment status, PEP status
    Performs sanctions and AML checks
    Tools: search_policies, check_compliance, get_policy_requirements
    """
    
    @staticmethod
    async def create() -> ChatAgent:
        """Create the Compliance agent with MCP tools."""
        tools = await get_maf_tools_for_agent([
            "search_policies",
            "check_compliance",
            "get_policy_requirements",
        ])
        
        chat_client = create_azure_chat_client()
        instructions = load_prompt("compliance")
        
        return chat_client.create_agent(
            name="compliance",
            description="Compliance Agent - performs regulatory compliance checks",
            instructions=instructions,
            tools=tools,
        )
