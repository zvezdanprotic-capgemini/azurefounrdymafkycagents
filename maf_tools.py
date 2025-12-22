"""
MAF Tool Wrappers for MCP Tools

Wraps MCP HTTP client tools so they can be used by Microsoft Agent Framework agents.
MAF agents accept regular Python functions decorated with @ai_function, not FunctionTool objects.
"""
import logging
from typing import Any, Dict, List, Optional, Callable
from agent_framework import ai_function
from mcp_client import get_mcp_client

logger = logging.getLogger("kyc.maf_tools")


class MCPToolWrapper:
    """Wrapper to convert MCP tools to MAF-compatible async functions."""
    
    def __init__(self, mcp_tool: Any):
        """
        Initialize wrapper with an MCP tool.
        
        Args:
            mcp_tool: MCP tool from MCP client
        """
        self.mcp_tool = mcp_tool
        self.name = mcp_tool.name
        self.description = mcp_tool.description or ""
        
    async def _execute(self, **kwargs) -> str:
        """Execute the underlying MCP tool."""
        try:
            # MCP tools have ainvoke for async execution
            if hasattr(self.mcp_tool, 'ainvoke'):
                result = await self.mcp_tool.ainvoke(kwargs)
            elif hasattr(self.mcp_tool, 'invoke'):
                result = self.mcp_tool.invoke(kwargs)
            else:
                # Fallback to direct call
                result = await self.mcp_tool(kwargs)
            
            # Convert result to string if needed
            if isinstance(result, str):
                return result
            elif isinstance(result, dict):
                import json
                return json.dumps(result, indent=2)
            else:
                return str(result)
                
        except Exception as e:
            logger.error(f"Error executing MCP tool {self.name}: {e}", exc_info=True)
            return f"Error: {str(e)}"
    
    def to_ai_function(self) -> Callable:
        """Convert to MAF ai_function-decorated callable."""
        # Create a wrapper function that MAF can call
        async def wrapped_tool(**kwargs) -> str:
            return await self._execute(**kwargs)
        
        # Set function metadata for MAF
        wrapped_tool.__name__ = self.name
        wrapped_tool.__doc__ = self.description
        
        # Apply @ai_function decorator
        return ai_function(wrapped_tool)


async def get_maf_tools_for_agent(tool_names: Optional[List[str]] = None) -> List[Callable]:
    """
    Get MAF-compatible tools from MCP client.
    
    Args:
        tool_names: Optional list of tool names to filter. If None, returns all tools.
        
    Returns:
        List of @ai_function decorated callables
    """
    try:
        mcp_client = get_mcp_client()
        if not mcp_client:
            logger.warning("MCP client not available, returning empty tool list")
            return []
        
        # Get all MCP tools from MCP client
        mcp_tools = await mcp_client.get_tools()
        
        # Filter if tool_names provided
        if tool_names:
            needed = set(tool_names)
            filtered_tools = []
            for tool in mcp_tools:
                name = tool.name
                # Handle namespaced names like "postgres__get_customer_by_email"
                base_name = name.split("__")[-1] if "__" in name else name
                if name in needed or base_name in needed:
                    filtered_tools.append(tool)
            mcp_tools = filtered_tools
        
        # Wrap each tool
        wrapped_maf_tools = []
        for mcp_tool in mcp_tools:
            wrapper = MCPToolWrapper(mcp_tool)
            maf_tool = wrapper.to_ai_function()
            wrapped_maf_tools.append(maf_tool)
            logger.debug(f"Wrapped MCP tool: {wrapper.name}")
        
        logger.info(f"Loaded {len(wrapped_maf_tools)} MAF tools from MCP client")
        return wrapped_maf_tools
        
    except Exception as e:
        logger.error(f"Error loading MAF tools: {e}", exc_info=True)
        return []


async def get_tools_by_category(category: str) -> List[Callable]:
    """
    Get tools by MCP server category.
    
    Args:
        category: One of 'postgres', 'blob', 'email', 'rag'
        
    Returns:
        List of @ai_function decorated callables for that category
    """
    try:
        mcp_client = get_mcp_client()
        if not mcp_client:
            return []
        
        all_tools = await mcp_client.get_tools()
        
        # Filter by category prefix (e.g., "postgres__")
        category_tools = [
            tool for tool in all_tools 
            if tool.name.startswith(f"{category}__")
        ]
        
        # Wrap tools
        wrapped_tools = []
        for mcp_tool in category_tools:
            wrapper = MCPToolWrapper(mcp_tool)
            wrapped_tools.append(wrapper.to_ai_function())
        
        logger.info(f"Loaded {len(wrapped_tools)} tools for category '{category}'")
        return wrapped_tools
        
    except Exception as e:
        logger.error(f"Error loading tools for category {category}: {e}", exc_info=True)
        return []
