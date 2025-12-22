"""
Recommendation Agent - Provides product/service recommendations
"""
from agent_framework import ChatAgent
from agents.utils import create_azure_chat_client, load_prompt
from maf_tools import get_maf_tools_for_agent


class RecommendationAgent:
    """
    Recommendation Agent - Provides product/service recommendations.
    
    Considers customer profile and preferences to recommend products
    Tools: get_customer_history, search_policies
    """
    
    @staticmethod
    async def create() -> ChatAgent:
        """Create the Recommendation agent with MCP tools."""
        tools = await get_maf_tools_for_agent([
            "get_customer_history",
            "search_policies",
        ])
        
        chat_client = create_azure_chat_client()
        instructions = load_prompt("recommendation")
        
        return chat_client.create_agent(
            name="recommendation",
            description="Recommendation Agent - provides product recommendations",
            instructions=instructions,
            tools=tools,
        )
