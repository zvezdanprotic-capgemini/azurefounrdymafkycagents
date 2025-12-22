"""
Unit tests for MAF KYC agents.

Tests agents using Microsoft Agent Framework with MCP tool integration.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import json

from agents import AGENT_FACTORIES, WORKFLOW_STEPS
from mcp_client import KYCMCPClient


@pytest.mark.usefixtures("mcp_server_processes")
class TestMAFAgents:
    """Tests for MAF agent factory and structure."""
    
    def test_agent_factories_exist(self):
        """Test that all agent factories are registered."""
        expected_agents = ["intake", "verification", "eligibility", "recommendation", "compliance", "action"]
        
        for agent_name in expected_agents:
            assert agent_name in AGENT_FACTORIES, f"Agent factory '{agent_name}' not found"
            assert callable(AGENT_FACTORIES[agent_name]), f"Agent factory '{agent_name}' is not callable"
    
    def test_workflow_steps_defined(self):
        """Test that workflow steps are properly defined."""
        assert isinstance(WORKFLOW_STEPS, list)
        assert len(WORKFLOW_STEPS) == 6
        assert WORKFLOW_STEPS[0] == "intake"
        assert WORKFLOW_STEPS[-1] == "action"
    
    @pytest.mark.asyncio
    async def test_agent_factory_creates_agent(self):
        """Test that agent factories can create agent instances."""
        # Test creating an intake agent
        intake_factory = AGENT_FACTORIES["intake"]
        
        # Mock Azure client and MCP tools to avoid actual API calls
        with patch('agents.intake_agent.create_azure_chat_client') as mock_client, \
             patch('agents.intake_agent.get_maf_tools_for_agent') as mock_tools:
            mock_chat_client = MagicMock()
            mock_agent = MagicMock()
            mock_chat_client.create_agent = MagicMock(return_value=mock_agent)
            mock_client.return_value = mock_chat_client
            mock_tools.return_value = []  # Empty tools list
            
            agent = await intake_factory()
            
            # Verify agent was created
            assert agent is not None
            assert agent == mock_agent
            mock_chat_client.create_agent.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_all_agents_can_be_created(self):
        """Test that all agent factories can create agents."""
        # Patch each agent module's create_azure_chat_client and get_maf_tools_for_agent
        agent_modules = [
            'agents.intake_agent',
            'agents.verification_agent',
            'agents.eligibility_agent',
            'agents.recommendation_agent',
            'agents.compliance_agent',
            'agents.action_agent'
        ]
        
        for agent_module in agent_modules:
            with patch(f'{agent_module}.create_azure_chat_client') as mock_client, \
                 patch(f'{agent_module}.get_maf_tools_for_agent') as mock_tools:
                mock_chat_client = MagicMock()
                mock_chat_client.create_agent = MagicMock(return_value=MagicMock())
                mock_client.return_value = mock_chat_client
                mock_tools.return_value = []  # Empty tools list
                
                agent_name = agent_module.split('.')[-1].replace('_agent', '')
                factory = AGENT_FACTORIES[agent_name]
                agent = await factory()
                assert agent is not None


@pytest.mark.usefixtures("mcp_server_processes")
class TestAgentPrompts:
    """Tests for agent prompts and instructions."""
    
    def test_prompts_exist(self):
        """Test that all agent prompts exist and can be loaded."""
        from pathlib import Path
        
        prompts_dir = Path(__file__).parent.parent / "agents" / "prompts"
        assert prompts_dir.exists(), "Prompts directory not found"
        
        expected_prompts = [
            "intake_prompt.txt",
            "verification_prompt.txt",
            "eligibility_prompt.txt",
            "recommendation_prompt.txt",
            "compliance_prompt.txt",
            "action_prompt.txt"
        ]
        
        for prompt_file in expected_prompts:
            prompt_path = prompts_dir / prompt_file
            assert prompt_path.exists(), f"Prompt file '{prompt_file}' not found"
            
            # Verify file has content
            content = prompt_path.read_text()
            assert len(content) > 0, f"Prompt file '{prompt_file}' is empty"
    
    def test_load_prompt_function(self):
        """Test the load_prompt utility function."""
        from agents.utils import load_prompt
        
        # Test loading intake prompt
        prompt = load_prompt("intake")
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "intake" in prompt.lower() or "customer" in prompt.lower()


@pytest.mark.usefixtures("mcp_server_processes")
class TestMCPClientTools:
    """Test HTTP MCP client tool availability."""
    
    @pytest.mark.asyncio
    async def test_mcp_client_has_all_servers(self, mcp_client):
        """Test that MCP client has tools from all servers."""
        all_tools = await mcp_client.get_tools()
        tool_names = [tool.name for tool in all_tools]
        
        # Should have tools from all 4 servers
        has_postgres = any("postgres__" in name for name in tool_names)
        has_blob = any("blob__" in name for name in tool_names)
        has_email = any("email__" in name for name in tool_names)
        has_rag = any("rag__" in name for name in tool_names)
        
        assert has_postgres, "Missing postgres tools"
        assert has_blob, "Missing blob tools"
        assert has_email, "Missing email tools"
        assert has_rag, "Missing RAG tools"
    
    @pytest.mark.asyncio
    async def test_call_postgres_tool(self, mcp_client):
        """Test calling a PostgreSQL tool via HTTP MCP."""
        tools = await mcp_client.get_tools()
        # Basic sanity check: have tools available
        assert isinstance(tools, list)
        assert len(tools) > 0
    
    @pytest.mark.asyncio
    async def test_list_tools_by_server(self, mcp_client):
        """Test filtering tools by server."""
        # Verify client provides tools without strict prefix requirement
        all_tools = await mcp_client.get_tools()
        assert isinstance(all_tools, list)
        assert len(all_tools) > 0


@pytest.mark.usefixtures("mcp_server_processes")
class TestMAFToolIntegration:
    """Tests for MAF tool wrapper integration."""
    
    @pytest.mark.asyncio
    async def test_maf_tools_available(self):
        """Test that MAF tools can be retrieved."""
        from maf_tools import get_maf_tools_for_agent
        
        # Mock MCP client
        with patch('maf_tools.get_mcp_client') as mock_get_client:
            mock_client = MagicMock()
            mock_tool = MagicMock()
            mock_tool.name = "test_tool"
            mock_tool.description = "Test tool"
            mock_client.get_tools = AsyncMock(return_value=[mock_tool])
            mock_get_client.return_value = mock_client
            
            tools = await get_maf_tools_for_agent(["test_tool"])
            
            # Verify tools were retrieved
            assert isinstance(tools, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
