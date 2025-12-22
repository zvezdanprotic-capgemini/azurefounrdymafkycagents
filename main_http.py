"""
Main FastAPI Application with HTTP MCP Client

This version uses HTTP MCP servers running as separate processes.
Each MCP server runs on its own port and agents connect via HTTP.

Before running this application:
1. Start all MCP servers: ./start_all_mcp_servers.sh
2. Verify servers are running on ports 8001-8004
3. Then start this FastAPI app: uvicorn main_http:app --reload --port 8000
"""
import os
import json
import uuid
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv

# Import HTTP MCP Client
from mcp_client import initialize_mcp_client, get_mcp_client

# Import MAF workflow (replaces Langgraph)
from maf_workflow_hitl import initialize_workflow, start_workflow, continue_workflow

# Import telemetry collector
from telemetry_collector import (
    TelemetryCollector,
    set_telemetry_collector,
    get_telemetry_collector,
    get_recent_telemetry,
    get_session_telemetry_stream,
)
import asyncpg

# Force-disable OpenTelemetry console exporters unless explicitly enabled
# This prevents JSON span dumps like mcp.get_tools from flooding the console.
if os.getenv("ENABLE_CONSOLE_EXPORTERS", "false").lower() != "true":
    os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
    os.environ.setdefault("OTEL_LOGS_EXPORTER", "none")
    os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")

# Configure OpenTelemetry observability (optional - gracefully degrades if not available)
try:
    from agent_framework.observability import configure_otel_providers, enable_instrumentation
    import logging
    logger = logging.getLogger(__name__)
    
    # Only enable in development/debugging - set ENABLE_INSTRUMENTATION=true in .env
    if os.getenv("ENABLE_INSTRUMENTATION", "false").lower() == "true":
        # Check if console exporters should be enabled (set ENABLE_CONSOLE_EXPORTERS=true for verbose logs)
        enable_console = os.getenv("ENABLE_CONSOLE_EXPORTERS", "false").lower() == "true"
        # Enable sensitive data to capture prompts, responses, and token usage (default: true for telemetry)
        enable_sensitive = os.getenv("ENABLE_SENSITIVE_DATA", "true").lower() == "true"
        
        # Disable console exporters explicitly to suppress JSON logs
        configure_otel_providers(enable_console_exporters=False)
        enable_instrumentation(enable_sensitive_data=enable_sensitive)
        logger.info(f"✓ OpenTelemetry instrumentation enabled (console exporters: DISABLED, sensitive_data: {enable_sensitive})")
    else:
        logger.info("OpenTelemetry instrumentation disabled (set ENABLE_INSTRUMENTATION=true to enable)")
except ImportError:
    pass  # OpenTelemetry integration is optional
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Failed to configure OpenTelemetry: {e}")

# Import error handling and tracing
from error_handling import (
    setup_app,
    ErrorHandlingConfig,
    handle_errors,
    trace_function,
    get_tracer,
    KYCError,
    ServiceUnavailableError,
    ValidationError,
    NotFoundError
)

# Load environment variables
load_dotenv()

# Configure application
SERVICE_NAME = "kyc-orchestrator"
VERSION = "4.0.0"

# Set up logger
import logging
logger = logging.getLogger(SERVICE_NAME)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and cleanup HTTP MCP client, MAF workflow, and telemetry."""
    app.state.logger = logger
    logger.info("Initializing HTTP MCP client, MAF workflow, and telemetry...")
    
    # Initialize PostgreSQL connection pool for telemetry
    db_pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "kyc_crm"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD"),
        min_size=2,
        max_size=10
    )
    app.state.db_pool = db_pool
    logger.info("PostgreSQL connection pool created")
    
    # Initialize telemetry collector
    telemetry_collector = TelemetryCollector(db_pool)
    await telemetry_collector.start()
    set_telemetry_collector(telemetry_collector)
    app.state.telemetry_collector = telemetry_collector
    logger.info("Telemetry collector initialized")
    
    # Initialize HTTP MCP client (connects to servers on ports 8001-8004)
    mcp_client = initialize_mcp_client(
        postgres_url=os.getenv("MCP_POSTGRES_URL", "http://127.0.0.1:8001/mcp"),
        blob_url=os.getenv("MCP_BLOB_URL", "http://127.0.0.1:8002/mcp"),
        email_url=os.getenv("MCP_EMAIL_URL", "http://127.0.0.1:8003/mcp"),
        rag_url=os.getenv("MCP_RAG_URL", "http://127.0.0.1:8004/mcp"),
    )
    
    # Initialize connection
    await mcp_client.initialize()
    app.state.mcp_client = mcp_client
    logger.info("HTTP MCP client initialized successfully")
    
    # Initialize MAF workflow
    logger.info("Initializing MAF workflow...")
    await initialize_workflow()
    logger.info("MAF workflow initialized successfully")
    
    yield
    
    # Cleanup
    logger.info("Shutting down services...")
    
    if telemetry_collector:
        await telemetry_collector.stop()
        logger.info("Telemetry collector stopped")
        
    await mcp_client.close()
    logger.info("HTTP MCP client shut down")
    
    await db_pool.close()
    logger.info("Database pool closed")

# Create FastAPI app
app = FastAPI(
    title=f"Azure AI Agents {SERVICE_NAME}", 
    version=VERSION,
    description="KYC system with HTTP MCP servers and Microsoft Agent Framework",
    lifespan=lifespan
)

# Configure error handling and tracing
config = ErrorHandlingConfig(
    service_name=SERVICE_NAME,
    environment=os.getenv("ENV", "development"),
    otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    enable_tracing=True,
    enable_error_handling=True
)

# Set up error handling, tracing, and request ID middleware
app = setup_app(app, config)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=json.loads(os.getenv("ALLOWED_ORIGINS", "[\"http://localhost:3000\", \"http://localhost:5173\"]")),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session persistence
SESSIONS_FILE = Path("sessions.json")


@trace_function()
def load_sessions() -> Dict[str, Any]:
    """Load sessions from file."""
    try:
        if SESSIONS_FILE.exists():
            with open(SESSIONS_FILE, "r") as f:
                return json.load(f)
        return {}
    except Exception as e:
        app.state.logger.error("Failed to load sessions", exc_info=True)
        return {}


@trace_function()
def save_sessions(sessions: Dict[str, Any]) -> None:
    """Save sessions to file."""
    try:
        with open(SESSIONS_FILE, "w") as f:
            json.dump(sessions, f, indent=2)
    except Exception as e:
        app.state.logger.error("Failed to save sessions", exc_info=True)
        raise ServiceUnavailableError("Session Storage", cause=e)


# Initialize sessions
sessions = load_sessions()


class ChatMessage(BaseModel):
    role: str
    content: str


class CustomerInput(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    insurance_needs: Optional[str] = None  # Frontend compatibility


class StartSessionResponse(BaseModel):
    session_id: str
    status: str
    message: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    status: str
    current_step: str
    customer: Dict[str, Any]
    request_id: Optional[str] = None  # For data requests
    is_data_request: bool = False  # Flag indicating user needs to provide data
    # Frontend compatibility fields
    session_status: Optional[str] = None
    agent_step: Optional[str] = None
    agent_label: Optional[str] = None
    decision: Optional[Dict[str, Any]] = None
    user_message: Optional[str] = None
    final: Optional[bool] = False
    passed: Optional[bool] = None
    advanced: Optional[bool] = False
    advancement: Optional[Dict[str, Any]] = None
    thread_id: Optional[str] = None
    run_id: Optional[str] = None


@app.get("/")
@handle_errors()
@trace_function()
async def root():
    """Health check endpoint."""
    return {
        "service": f"{SERVICE_NAME} with HTTP MCP and MAF",
        "version": VERSION,
        "status": "running",
        "orchestration": "Microsoft Agent Framework (MAF)",
        "mcp_architecture": "HTTP (decoupled servers)",
        "mcp_servers": {
            "postgres": os.getenv("MCP_POSTGRES_URL", "http://127.0.0.1:8001/mcp"),
            "blob": os.getenv("MCP_BLOB_URL", "http://127.0.0.1:8002/mcp"),
            "email": os.getenv("MCP_EMAIL_URL", "http://127.0.0.1:8003/mcp"),
            "rag": os.getenv("MCP_RAG_URL", "http://127.0.0.1:8004/mcp"),
        }
    }


@app.get("/health")
@handle_errors()
@trace_function()
async def health():
    """Detailed health check including MCP server connectivity."""
    mcp_client = get_mcp_client()
    
    # Check if MCP client is connected
    if not mcp_client or not hasattr(mcp_client, 'is_connected') or not mcp_client.is_connected():
        from error_handling import KYCError, ErrorCode
        raise KYCError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="MCP client is not connected",
            status_code=503,
            details={"service": "MCP Client"}
        )
    
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": VERSION,
        "mcp_connected": True,
        "mcp_client": "connected"
    }


@app.post("/start-session", response_model=StartSessionResponse)
@handle_errors()
@trace_function()
async def start_session(customer: CustomerInput):
    """
    Start a new KYC session.
    Frontend compatibility endpoint.
    """
    session_id = str(uuid.uuid4())
    
    sessions[session_id] = {
        "session_id": session_id,
        "status": "active",
        "customer": customer.dict(exclude_none=True),
        "chat_history": [],
        "current_step": "intake",
        "step_results": {},
        "pending_request_id": None,
        "agent_step": "intake",
        "agent_label": "Intake Agent"
    }
    
    # Immediately run first agent turn so the user sees a greeting/question on load
    try:
        from agent_framework import RequestInfoEvent, WorkflowOutputEvent
        from maf_workflow_hitl import DataRequest
        telemetry = get_telemetry_collector()

        # Construct an initial message from provided customer info
        cust = sessions[session_id]["customer"]
        initial_msg = (
            f"Start KYC for {cust.get('name','customer')} ({cust.get('email','unknown email')}). "
            f"Insurance needs: {cust.get('insurance_needs','unspecified')}."
        )

        stream = await start_workflow(initial_msg, session_id=session_id)
        events = [event async for event in stream]

        ai_response = None
        request_id = None

        for event in events:
            if isinstance(event, RequestInfoEvent):
                if isinstance(event.data, DataRequest):
                    ai_response = event.data.prompt
                    request_id = event.request_id
                    sessions[session_id]["current_step"] = event.data.step
                    sessions[session_id]["pending_request_id"] = request_id
                    # Log request telemetry
                    if telemetry:
                        telemetry.log_request_event(
                            session_id=session_id,
                            request_id=request_id,
                            request_type="info_request",
                            prompt=ai_response,
                            step_name=event.data.step,
                        )
                    break
            elif isinstance(event, WorkflowOutputEvent):
                # Fallback: if workflow yields output, show it as assistant message
                ai_response = str(event.data)
                break

        # Seed chat history with a friendly greeting + the first agent prompt if available
        greeting = "Welcome to the KYC assistant. I'll guide you through the required steps."
        sessions[session_id]["chat_history"].append({
            "role": "assistant",
            "content": greeting,
            "timestamp": str(asyncio.get_event_loop().time())
        })
        if ai_response:
            sessions[session_id]["chat_history"].append({
                "role": "assistant",
                "content": ai_response,
                "timestamp": str(asyncio.get_event_loop().time())
            })
    except Exception as e:
        # Non-fatal: if warm-up fails, user can still chat to trigger flow
        app.state.logger.warning(f"Initial agent turn failed for session {session_id}: {e}")

    save_sessions(sessions)
    
    return StartSessionResponse(
        session_id=session_id,
        status="active",
        message="KYC session started. Send your first message to begin."
    )


@app.post("/chat", response_model=ChatResponse)
@handle_errors()
@trace_function(attributes={"component": "chat_endpoint"})
async def chat(request: ChatRequest):
    """
    Main chat endpoint for KYC workflow with human-in-the-loop support.
    
    Uses Microsoft Agent Framework (MAF) with HTTP MCP clients and request_info pattern.
    """
    from agent_framework import RequestInfoEvent, WorkflowOutputEvent, WorkflowStatusEvent
    from maf_workflow_hitl import DataRequest
    
    # Get telemetry collector
    telemetry = get_telemetry_collector()
    
    # Get or create session with trace context
    session_id = request.session_id or str(uuid.uuid4())
    
    with get_tracer(__name__).start_as_current_span("process_chat") as span:
        span.set_attribute("session_id", session_id)
        span.set_attribute("has_session_id", bool(request.session_id))
        
        if session_id not in sessions:
            sessions[session_id] = {
                "session_id": session_id,
                "status": "active",
                "customer": {},
                "chat_history": [],
                "current_step": "intake",
                "step_results": {},
                "pending_request_id": None,
                "agent_step": "intake",
                "agent_label": "Intake Agent"
            }
        
        session = sessions[session_id]
        
        # Add user message to history
        session["chat_history"].append({
            "role": "user",
            "content": request.message,
            "timestamp": str(asyncio.get_event_loop().time())
        })
        
        # Determine if this is a new workflow or continuing with responses
        if session.get("pending_request_id"):
            # User is responding to a data request
            pending_id = session["pending_request_id"]
            responses = {pending_id: request.message}
            
            # Continue workflow with user's response (pass session_id)
            stream = await continue_workflow(responses, session_id=session_id)
            
            # Clear pending request
            session["pending_request_id"] = None
        else:
            # Start new workflow or send new message (pass session_id)
            stream = await start_workflow(request.message, session_id=session_id)
        
        # Collect events from workflow stream
        events = [event async for event in stream]
        
        # Process events
        ai_response = None
        request_id = None
        is_data_request = False
        workflow_output = None
        
        for event in events:
            if isinstance(event, RequestInfoEvent):
                # Agent needs more information from user
                if isinstance(event.data, DataRequest):
                    ai_response = event.data.prompt
                    request_id = event.request_id
                    is_data_request = True
                    session["current_step"] = event.data.step
                    session["pending_request_id"] = request_id
                    app.state.logger.info(f"Data request from step {event.data.step}: {ai_response[:100]}")
                    
                    # Log request event
                    if telemetry:
                        telemetry.log_request_event(
                            session_id=session_id,
                            request_id=request_id,
                            request_type="info_request",
                            prompt=ai_response,
                            step_name=event.data.step,
                        )
                    
            elif isinstance(event, WorkflowOutputEvent):
                # Workflow output - could be completion or customer data update
                workflow_output = str(event.data)
                try:
                    output_data = json.loads(workflow_output)
                    
                    if output_data.get("type") == "customer_data_update":
                        # Customer data was updated by an agent
                        session["customer"] = output_data.get("data", {})
                        app.state.logger.info(f"Customer data updated at step {output_data.get('step')}: {list(session['customer'].keys())}")
                        
                    elif output_data.get("status") == "complete":
                        ai_response = f"KYC workflow completed successfully! {output_data.get('notes', '')}"
                        session["status"] = "complete"
                        session["customer"] = output_data.get("customer_data", session.get("customer", {}))
                        
                        # Log workflow completion
                        if telemetry:
                            telemetry.log_workflow_event(
                                session_id=session_id,
                                workflow_id=session_id,
                                workflow_status="completed",
                                current_step="action",
                                total_steps=6,
                                completed_steps=6,
                                data_collected=session["customer"],
                            )
                        
                    elif output_data.get("status") == "failed":
                        ai_response = f"Workflow failed at {output_data.get('step')}: {output_data.get('reason')}"
                        session["status"] = "failed"
                        
                        # Log workflow failure
                        if telemetry:
                            telemetry.log_error(
                                session_id=session_id,
                                error_type="WorkflowError",
                                error_message=output_data.get('reason', 'Unknown error'),
                                component="workflow",
                                operation="execute_workflow",
                                severity="error",
                            )
                except json.JSONDecodeError:
                    # Plain text output
                    if not ai_response:
                        ai_response = workflow_output
        
        if not ai_response:
            ai_response = "Processing your request..."
        
        # Update session
        session["chat_history"].append({
            "role": "assistant",
            "content": ai_response,
            "timestamp": str(asyncio.get_event_loop().time())
        })
        
        # Update agent tracking
        agent_map = {
            "intake": "Intake Agent",
            "verification": "Verification Agent",
            "eligibility": "Eligibility Agent",
            "recommendation": "Recommendation Agent",
            "compliance": "Compliance Agent",
            "action": "Action Agent"
        }
        session["agent_step"] = session["current_step"]
        session["agent_label"] = agent_map.get(session["current_step"], "Agent")
        
        # Save sessions
        save_sessions(sessions)
        
        # Add trace attributes
        span.set_attribute("response_length", len(ai_response))
        span.set_attribute("current_step", session["current_step"])
        span.set_attribute("is_data_request", is_data_request)
        
        return ChatResponse(
            response=ai_response,
            session_id=session_id,
            status=session["status"],
            current_step=session["current_step"],
            customer=session["customer"],
            request_id=request_id,
            is_data_request=is_data_request,
            session_status=session["status"],
            agent_step=session["agent_step"],
            agent_label=session["agent_label"],
            user_message=request.message,
            final=not is_data_request,
            passed=session["status"] != "failed",
            advanced=False,
            advancement=None
        )


@app.post("/chat/{session_id}", response_model=ChatResponse)
@handle_errors()
@trace_function(attributes={"component": "chat_endpoint_with_session"})
async def chat_with_session(session_id: str, message: ChatMessage):
    """
    Chat endpoint with session ID in path (frontend compatibility).
    """
    # Convert ChatMessage to ChatRequest format
    chat_request = ChatRequest(
        message=message.content,
        session_id=session_id
    )
    
    # Reuse the main chat endpoint logic
    return await chat(chat_request)


@app.get("/sessions")
@handle_errors()
@trace_function()
async def list_sessions():
    """List all active sessions."""
    return {"sessions": list(sessions.values())}


@app.get("/session/{session_id}")
@handle_errors()
@trace_function(attributes={"component": "get_session"})
async def get_session(session_id: str):
    """Get session details."""
    if session_id not in sessions:
        raise NotFoundError(resource="Session", id=session_id, message="Session not found")
    return sessions[session_id]


@app.delete("/session/{session_id}")
@handle_errors()
@trace_function(attributes={"component": "delete_session"})
async def delete_session(session_id: str):
    """Delete a session."""
    if session_id in sessions:
        del sessions[session_id]
        save_sessions(sessions)
        return {"deleted": True, "session_id": session_id}
    raise NotFoundError(resource="Session", id=session_id, message="Session not found")

@app.get("/steps")
@handle_errors()
@trace_function()
async def get_workflow_steps():
    """Get available workflow steps."""
    from agents import WORKFLOW_STEPS
    
    steps = [
        {
            "id": step,
            "name": step.replace("_", " ").title(),
            "description": f"{step.replace('_', ' ').title()} stage of KYC process",
            "order": idx
        }
        for idx, step in enumerate(WORKFLOW_STEPS, 1)
    ]
    
    return {"steps": steps}


@app.get("/session/{session_id}/panel-data")
@handle_errors()
@trace_function()
async def get_session_panel_data(session_id: str):
    """Get session panel data (workflow state, agent responses, CRM data, documents)."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Build the response matching SessionPanelData interface
    panel_data = {
        "session": {
            "session_id": session_id,
            "customer": session.get("customer", {}),
            "current_step": session.get("current_step", ""),
            "status": session.get("status", "active"),
        },
        "crm": session.get("crm_data", {"found": False}),
        "previous_sessions": {
            "sessions": session.get("previous_sessions", []),
            "error": None
        },
        "documents": {
            "document_count": len(session.get("documents", [])),
            "documents": session.get("documents", []),
            "error": None,
            "folder": session.get("blob_folder", ""),
            "account_id": session.get("crm_data", {}).get("account", {}).get("id")
        }
    }
    
    return panel_data


@app.put("/session/{session_id}")
@handle_errors()
@trace_function(attributes={"component": "update_session"})
async def update_session(session_id: str, update: Dict[str, Any]):
    """Update session data."""
    if session_id not in sessions:
        raise NotFoundError(resource="Session", id=session_id, message="Session not found")
    
    session = sessions[session_id]
    
    # Update allowed fields
    if "customer" in update:
        session["customer"].update(update["customer"])
    if "status" in update:
        session["status"] = update["status"]
    if "current_step" in update:
        session["current_step"] = update["current_step"]
    
    save_sessions(sessions)
    
    return {"status": "updated", "session_id": session_id}


@app.post("/run-step/{session_id}")
@handle_errors()
@trace_function(attributes={"component": "run_step"})
async def run_step(session_id: str, step_data: Dict[str, Any] = None):
    """
    Run a specific workflow step (legacy endpoint for compatibility).
    Now redirects to the chat-based workflow.
    """
    if session_id not in sessions:
        raise NotFoundError(resource="Session", id=session_id, message="Session not found")
    
    # This is a legacy endpoint - redirect to chat
    step = step_data.get("step") if step_data else None
    message = f"Continue with {step} step" if step else "Continue workflow"
    
    chat_request = ChatRequest(message=message, session_id=session_id)
    return await chat(chat_request)

@app.get("/mcp/tools")
@handle_errors()
@trace_function(attributes={"component": "list_mcp_tools"})
async def list_mcp_tools():
    """List all available MCP tools from HTTP servers."""
    mcp_client = get_mcp_client()
    if not mcp_client or not hasattr(mcp_client, 'get_tools'):
        raise ServiceUnavailableError("MCP Client", "MCP client is not available")
        
    tools = await mcp_client.get_tools()
    
    # Serialize tools to dict format
    tools_data = []
    for tool in tools:
        tool_info = {
            "name": tool.name,
            "description": tool.description,
        }
        # Add input schema if available
        if hasattr(tool, 'args_schema') and tool.args_schema:
            try:
                tool_info["input_schema"] = tool.args_schema.model_json_schema()
            except:
                pass
        tools_data.append(tool_info)
    
    return {
        "total_tools": len(tools_data),
        "tools": tools_data
    }


@app.get("/mcp/servers")
@handle_errors()
@trace_function(attributes={"component": "list_mcp_servers"})
async def list_mcp_servers():
    """List MCP server configuration."""
    return {
        "servers": {
            "postgres": os.getenv("MCP_POSTGRES_URL", "http://127.0.0.1:8001/mcp"),
            "blob": os.getenv("MCP_BLOB_URL", "http://127.0.0.1:8002/mcp"),
            "email": os.getenv("MCP_EMAIL_URL", "http://127.0.0.1:8003/mcp"),
            "rag": os.getenv("MCP_RAG_URL", "http://127.0.0.1:8004/mcp"),
        }
    }


# ==================== Telemetry Endpoints ====================

@app.get("/telemetry/recent")
@handle_errors()
@trace_function(attributes={"component": "telemetry_recent"})
async def get_recent_telemetry_endpoint(
    session_id: Optional[str] = None,
    limit: int = 50
):
    """Get recent telemetry events."""
    db_pool = app.state.db_pool
    telemetry_data = await get_recent_telemetry(db_pool, session_id, limit)
    
    # Convert datetime objects to ISO strings for JSON serialization
    for event in telemetry_data:
        if 'timestamp' in event and event['timestamp']:
            event['timestamp'] = event['timestamp'].isoformat()
    
    return {
        "total": len(telemetry_data),
        "events": telemetry_data
    }


@app.get("/telemetry/session/{session_id}")
@handle_errors()
@trace_function(attributes={"component": "telemetry_session"})
async def get_session_telemetry_endpoint(session_id: str):
    """Get all telemetry events for a specific session."""
    db_pool = app.state.db_pool
    telemetry_data = await get_recent_telemetry(db_pool, session_id, limit=1000)
    
    # Convert datetime objects to ISO strings
    for event in telemetry_data:
        if 'timestamp' in event and event['timestamp']:
            event['timestamp'] = event['timestamp'].isoformat()
    
    return {
        "session_id": session_id,
        "total": len(telemetry_data),
        "events": telemetry_data
    }


from fastapi.responses import StreamingResponse

@app.get("/telemetry/stream/{session_id}")
@handle_errors()
async def stream_session_telemetry(session_id: str):
    """Stream telemetry events for a session (Server-Sent Events)."""
    
    async def event_generator():
        """Generate SSE events for telemetry."""
        db_pool = app.state.db_pool
        
        async for event in get_session_telemetry_stream(db_pool, session_id):
            # Convert datetime to ISO string
            if 'timestamp' in event and event['timestamp']:
                event['timestamp'] = event['timestamp'].isoformat()
            
            # Convert UUID to string
            if 'event_id' in event and event['event_id']:
                event['event_id'] = str(event['event_id'])
            
            # Format as SSE
            event_data = json.dumps(event)
            yield f"data: {event_data}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/telemetry/stats/{session_id}")
@handle_errors()
@trace_function(attributes={"component": "telemetry_stats"})
async def get_session_telemetry_stats(session_id: str):
    """Get aggregated statistics for a session."""
    db_pool = app.state.db_pool
    
    async with db_pool.acquire() as conn:
        # Get summary stats
        summary = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_events,
                COUNT(DISTINCT agent_name) as agents_used,
                SUM(duration_ms) as total_duration_ms,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as errors,
                MIN(timestamp) as started_at,
                MAX(timestamp) as last_activity
            FROM telemetry_events
            WHERE session_id = $1
        """, session_id)
        
        # Get agent breakdown
        agent_stats = await conn.fetch("""
            SELECT 
                agent_name,
                COUNT(*) as calls,
                AVG(execution_time_ms) as avg_duration_ms,
                SUM(total_tokens) as total_tokens
            FROM agent_metrics
            WHERE session_id = $1
            GROUP BY agent_name
        """, session_id)
        
        # Get tool breakdown
        tool_stats = await conn.fetch("""
            SELECT 
                tool_name,
                tool_server,
                COUNT(*) as calls,
                AVG(execution_time_ms) as avg_duration_ms,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors
            FROM tool_metrics
            WHERE session_id = $1
            GROUP BY tool_name, tool_server
        """, session_id)
        
        return {
            "session_id": session_id,
            "summary": dict(summary) if summary else {},
            "agents": [dict(row) for row in agent_stats],
            "tools": [dict(row) for row in tool_stats]
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
