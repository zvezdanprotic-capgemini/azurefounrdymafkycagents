"""
Verification Agent - Verifies customer identity and documents
"""
from agent_framework import ChatAgent
from agents.utils import create_azure_chat_client, load_prompt
from maf_tools import get_maf_tools_for_agent


class VerificationAgent:
    """
    Verification Agent - Verifies customer identity and documents.
    
    Required fields: document_type, document_number, document_expiry
    Tools: list_customer_documents, get_document_url
    """
    
    @staticmethod
    async def create() -> ChatAgent:
        """Create the Verification agent with MCP tools."""
        tools = await get_maf_tools_for_agent([
            "list_customer_documents",
            "get_document_url",
        ])
        
        chat_client = create_azure_chat_client()
        instructions = load_prompt("verification")
        
        return chat_client.create_agent(
            name="verification",
            description="Identity Verification Agent - verifies customer identity",
            instructions=instructions,
            tools=tools,
        )
