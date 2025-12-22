"""
Action Agent - Takes final actions based on workflow results
"""
from agent_framework import ChatAgent
from agents.utils import create_azure_chat_client, load_prompt
from maf_tools import get_maf_tools_for_agent


class ActionAgent:
    """
    Action Agent - Takes final actions based on workflow results.
    
    Creates accounts, sends confirmations when all checks pass
    Tools: send_kyc_approved_email, send_kyc_pending_email, save_kyc_session_state
    """
    
    @staticmethod
    async def create() -> ChatAgent:
        """Create the Action agent with MCP tools."""
        tools = await get_maf_tools_for_agent([
            "send_kyc_approved_email",
            "send_kyc_pending_email",
            "save_kyc_session_state",
        ])
        
        chat_client = create_azure_chat_client()
        instructions = load_prompt("action")
        
        return chat_client.create_agent(
            name="action",
            description="Action Agent - takes final actions",
            instructions=instructions,
            tools=tools,
        )
