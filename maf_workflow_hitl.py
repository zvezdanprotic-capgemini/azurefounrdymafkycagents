"""
MAF KYC Workflow with Human-in-the-Loop

Implements proper human-in-the-loop pattern using:
- ctx.request_info() when agents need data from user
- @response_handler to process user responses
- Executor pattern to coordinate agent <-> human interaction
"""
import json
import logging
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pydantic import BaseModel

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatAgent,
    ChatMessage,
    Executor,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)

from agents import AGENT_FACTORIES, WORKFLOW_STEPS

logger = logging.getLogger("kyc.maf_workflow")

# Import telemetry collector - use the global instance from main_http
def get_telemetry_collector():
    """Get the global telemetry collector instance."""
    try:
        from telemetry_collector import get_telemetry_collector as get_global_telemetry
        return get_global_telemetry()
    except Exception as e:
        logger.warning(f"Could not get telemetry collector: {e}")
        return None


@dataclass
class DataRequest:
    """Request sent to user when agent needs more information."""
    prompt: str
    step: str  # Which KYC step needs the data


class KYCTurnManager(Executor):
    """
    Coordinates turns between KYC agents and the human user.
    
    Responsibilities:
    - Start with intake agent
    - After each agent response, check if data is missing
    - If missing: request_info from human
    - If complete: move to next agent
    - Track current step and customer data
    """
    
    def __init__(self, id: str = "kyc_turn_manager", session_id: str = None):
        super().__init__(id=id)
        self.current_step_index = 0
        self.customer_data: Dict[str, Any] = {}
        self.session_id = session_id
        self.agent_start_times: Dict[str, float] = {}  # Track agent invocation timing
        
    @handler
    async def start(self, user_message: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        """
        Start KYC workflow with user's initial message.
        """
        logger.info(f"Starting KYC workflow with message: {user_message}")
        
        # Start with intake agent
        self.current_step_index = 0
        current_step = WORKFLOW_STEPS[self.current_step_index]
        
        # Build context-aware prompt for agent
        context_prompt = self._build_agent_prompt(user_message, current_step)
        
        # Track agent invocation start time
        self.agent_start_times[current_step] = time.time()
        
        # Send to current agent
        await ctx.send_message(
            AgentExecutorRequest(
                messages=[ChatMessage(Role.USER, text=context_prompt)],
                should_respond=True
            ),
            target_id=current_step
        )
    
    @handler
    async def on_agent_response(
        self,
        result: AgentExecutorResponse,
        ctx: WorkflowContext,
    ) -> None:
        """
        Handle agent's response - check if it needs user input or can proceed.
        """
        agent_text = result.agent_run_response.text
        current_step = WORKFLOW_STEPS[self.current_step_index]
        
        logger.info(f"Agent {current_step} responded: {agent_text[:200]}...")
        
        # Calculate agent execution time
        duration_ms = None
        if current_step in self.agent_start_times:
            duration_ms = int((time.time() - self.agent_start_times[current_step]) * 1000)
            del self.agent_start_times[current_step]
        
        # Extract token usage from agent response if available (robust across shapes)
        def _safe_get(obj, path: list[str]):
            cur = obj
            for key in path:
                if cur is None:
                    return None
                # support attr and dict
                if isinstance(cur, dict):
                    cur = cur.get(key)
                else:
                    cur = getattr(cur, key, None)
            return cur

        tokens = None
        prompt_tokens = None
        completion_tokens = None

        try:
            # Known locations for usage
            candidates = [
                _safe_get(result, ["agent_run_response", "usage"]),
                _safe_get(result, ["agent_run_response", "model_response", "usage"]),
                _safe_get(result, ["usage"]),
                _safe_get(result, ["agent_run_response", "additional_metadata", "usage"]),
                _safe_get(result, ["agent_run_response", "raw_response", "usage"]),
            ]

            usage = next((u for u in candidates if u), None)

            # If usage looks like JSON string, try parse
            if isinstance(usage, str):
                try:
                    import json as _json
                    usage = _json.loads(usage)
                except Exception:
                    pass

            if usage:
                # handle both attribute and dict
                def _val(u, *names):
                    for n in names:
                        v = (u.get(n) if isinstance(u, dict) else getattr(u, n, None))
                        if v is not None:
                            return v
                    return None

                prompt_tokens = _val(usage, "prompt_tokens", "input_tokens", "input_token_count")
                completion_tokens = _val(usage, "completion_tokens", "output_tokens", "output_token_count")
                if (prompt_tokens is not None) or (completion_tokens is not None):
                    pt = int(prompt_tokens or 0)
                    ct = int(completion_tokens or 0)
                    tokens = pt + ct
                    logger.info(f"✓ Token usage detected - prompt: {pt}, completion: {ct}, total: {tokens}")
            else:
                logger.info("No usage structure found on agent response; tokens will be inferred from OTel if present.")

        except Exception as e:
            logger.debug(f"Token extraction failed: {e}")
        
        # Log agent telemetry with OpenTelemetry context
        if self.session_id:
            telemetry = get_telemetry_collector()
            if telemetry:
                # Pass token information explicitly (falls back to OTel enrichment if present)
                telemetry.log_agent_event(
                    session_id=self.session_id,
                    agent_name=current_step,
                    event_name=f"agent_{current_step}_response",
                    status="completed",
                    duration_ms=duration_ms,
                    tokens=tokens,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    metadata={"response_length": len(agent_text)}
                )
        
        # Try to parse as JSON decision
        try:
            decision = json.loads(agent_text)
            
            # Check if it's a decision (has "decision" field) or a question
            if "decision" in decision and decision["decision"] in ["PASS", "REVIEW", "FAIL"]:
                # Agent made a decision - update customer data
                if "data_collected" in decision:
                    self.customer_data.update(decision["data_collected"])
                    # Emit customer data update event for API to capture
                    await ctx.yield_output(json.dumps({
                        "type": "customer_data_update",
                        "data": self.customer_data,
                        "step": current_step
                    }))
                
                if decision["decision"] == "PASS":
                    # Move to next step
                    logger.info(f"Step {current_step} passed. Customer data: {self.customer_data}")
                    await self._advance_to_next_step(ctx, decision.get("notes", "Step completed"))
                elif decision["decision"] == "FAIL":
                    # Workflow failed
                    await ctx.yield_output(json.dumps({
                        "status": "failed",
                        "step": current_step,
                        "reason": decision.get("reason", "Step failed"),
                        "notes": decision.get("notes", "")
                    }))
                else:  # REVIEW
                    # Need human input
                    prompt = decision.get("user_message", "Additional information needed")
                    await ctx.request_info(
                        request_data=DataRequest(prompt=prompt, step=current_step),
                        response_type=str
                    )
            else:
                # Not a decision JSON - treat as question for user
                await ctx.request_info(
                    request_data=DataRequest(prompt=agent_text, step=current_step),
                    response_type=str
                )
        except json.JSONDecodeError:
            # Plain text response - likely a question for the user
            await ctx.request_info(
                request_data=DataRequest(prompt=agent_text, step=current_step),
                response_type=str
            )
    
    @response_handler
    async def on_user_response(
        self,
        original_request: DataRequest,
        user_input: str,
        ctx: WorkflowContext[AgentExecutorRequest],
    ) -> None:
        """
        User provided information - send it back to the agent.
        """
        logger.info(f"User provided: {user_input}")
        
        # Build context with user's response
        current_step = WORKFLOW_STEPS[self.current_step_index]
        context_prompt = self._build_agent_prompt(user_input, current_step)
        
        # Send user's response to the current agent
        await ctx.send_message(
            AgentExecutorRequest(
                messages=[ChatMessage(Role.USER, text=context_prompt)],
                should_respond=True
            ),
            target_id=current_step
        )
    
    async def _advance_to_next_step(self, ctx: WorkflowContext, notes: str) -> None:
        """Move to the next step in the workflow."""
        self.current_step_index += 1
        
        if self.current_step_index >= len(WORKFLOW_STEPS):
            # Workflow complete!
            await ctx.yield_output(json.dumps({
                "status": "complete",
                "notes": notes,
                "customer_data": self.customer_data
            }))
        else:
            # Continue to next step
            next_step = WORKFLOW_STEPS[self.current_step_index]
            logger.info(f"Advancing to step: {next_step}")
            
            # Build prompt for next agent with accumulated context
            context_prompt = self._build_agent_prompt(
                f"Continue to {next_step} step", 
                next_step
            )
            
            await ctx.send_message(
                AgentExecutorRequest(
                    messages=[ChatMessage(Role.USER, text=context_prompt)],
                    should_respond=True
                ),
                target_id=next_step
            )
    
    def _build_agent_prompt(self, user_message: str, step: str) -> str:
        """Build context-aware prompt for agent."""
        return f"""
Customer Information:
{json.dumps(self.customer_data, indent=2) if self.customer_data else "No customer data yet"}

Current Stage: {step}
Progress: Step {self.current_step_index + 1} of {len(WORKFLOW_STEPS)}

User Message: {user_message}

Please process this information and respond with your JSON decision or ask for missing information.
"""


# Global workflow instance (keyed by session for multi-session support)
_workflows: Dict[str, Any] = {}


async def initialize_workflow(session_id: str = "default"):
    """Initialize the KYC workflow with human-in-the-loop support."""
    global _workflows
    
    if session_id in _workflows:
        return _workflows[session_id]
    
    logger.info(f"Initializing KYC workflow for session {session_id}")
    
    # Build workflow with TurnManager <-> Agents pattern
    builder = WorkflowBuilder()
    
    # Pre-create all agents (since factories are now async)
    logger.info("Pre-creating agents with tool loading...")
    agents = {}
    for step_name, agent_factory in AGENT_FACTORIES.items():
        logger.info(f"Creating {step_name} agent...")
        agent = await agent_factory()
        agents[step_name] = agent
        
        # Register with a simple lambda that returns the pre-created agent
        builder = builder.register_agent(lambda a=agent: a, name=step_name)
    
    # Register the turn manager with session_id
    builder = builder.register_executor(
        lambda: KYCTurnManager(id="kyc_turn_manager", session_id=session_id),
        name="kyc_turn_manager"
    )
    
    # Set turn manager as start
    builder = builder.set_start_executor("kyc_turn_manager")
    
    # Add edges: TurnManager -> Each Agent -> TurnManager
    for step_name in WORKFLOW_STEPS:
        builder = builder.add_edge("kyc_turn_manager", step_name)
        builder = builder.add_edge(step_name, "kyc_turn_manager")
    
    _workflows[session_id] = builder.build()
    logger.info(f"KYC workflow initialized successfully for session {session_id}")
    
    return _workflows[session_id]


async def start_workflow(user_message: str, session_id: str = "default"):
    """
    Start a new workflow run.
    
    Returns:
        Async generator of events from the workflow stream
    """
    workflow = await initialize_workflow(session_id)
    return workflow.run_stream(user_message)


async def continue_workflow(responses: Dict[str, str], session_id: str = "default"):
    """
    Continue workflow with user responses to data requests.
    
    Args:
        responses: Map of request_id -> user_response
        
    Returns:
        Async generator of events from the workflow stream
    """
    workflow = await initialize_workflow(session_id)
    return workflow.send_responses_streaming(responses)
