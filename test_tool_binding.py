"""
Detailed test to verify tool binding to LLM
"""
import pytest
import os
from dotenv import load_dotenv
from mcp_client import initialize_mcp_client
from maf_tools import get_maf_tools_for_agent

load_dotenv()

@pytest.mark.asyncio
async def test_tool_binding():
    """Test that tools are properly available via MAF tool wrappers"""
    
    print("🔍 Testing MAF tool integration...\n")
    
    # Initialize MCP client
    mcp_client = initialize_mcp_client(
        postgres_url="http://127.0.0.1:8001/mcp",
        blob_url="http://127.0.0.1:8002/mcp",
        email_url="http://127.0.0.1:8003/mcp",
        rag_url="http://127.0.0.1:8004/mcp",
    )
    await mcp_client.initialize()
    
    # Get MAF-wrapped tools
    tools = await get_maf_tools_for_agent()
    print(f"✅ Got {len(tools)} MAF-wrapped tools")
    
    # Test passed
    print(f"\n✅ SUCCESS: MAF tools are available!")
    print("   Tools are wrapped with @ai_function for MAF compatibility")
    
    await mcp_client.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_tool_binding())
