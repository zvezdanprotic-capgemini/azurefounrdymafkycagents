"""
Intake Agent - Collects initial customer information
"""
from agent_framework import ChatAgent
from agents.utils import create_azure_chat_client, load_prompt
from maf_tools import get_maf_tools_for_agent


class IntakeAgent:
    """
    Intake Agent - Collects initial customer information.
    
    Required fields: name, email, phone, address
    Tools: get_customer_by_email, get_customer_history
    """
    
    @staticmethod
    async def create() -> ChatAgent:
        """Create the Intake agent with MCP tools."""
        tools = await get_maf_tools_for_agent([
            "get_customer_by_email",
            "get_customer_history",
        ])
        
        chat_client = create_azure_chat_client()
        instructions = load_prompt("intake")
        
        return chat_client.create_agent(
            name="intake",
            description="Customer Intake Agent - collects essential customer information",
            instructions=instructions,
            tools=tools,
        )
