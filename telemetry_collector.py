"""
Telemetry Collector for MAF Agent Framework
Captures observability events and stores them in PostgreSQL

Uses OpenTelemetry for distributed tracing integration.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

import asyncpg
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    logger.warning("OpenTelemetry not available - trace context will not be captured")

logger = logging.getLogger("telemetry.collector")

# Simple in-memory cache for usage by trace_id (hex string)
_trace_usage_cache: Dict[str, Dict[str, int]] = {}

def register_trace_usage(trace_id_hex: str, input_tokens: Optional[int], output_tokens: Optional[int]):
    """Register token usage for a trace (called from span processor)."""
    if not trace_id_hex:
        return
    try:
        pt = int(input_tokens or 0)
        ct = int(output_tokens or 0)
        _trace_usage_cache[trace_id_hex] = {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct}
    except Exception:
        pass

def get_trace_usage(trace_id_hex: str) -> Optional[Dict[str, int]]:
    """Get cached usage for a trace if available."""
    return _trace_usage_cache.get(trace_id_hex)


class TelemetryCollector:
    """Collects and stores telemetry events in PostgreSQL."""
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.buffer: List[Dict[str, Any]] = []
        self.buffer_size = 10
        self.flush_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the telemetry collector."""
        self.flush_task = asyncio.create_task(self._auto_flush())
        logger.info("Telemetry collector started")
        
    async def stop(self):
        """Stop the telemetry collector and flush remaining events."""
        if self.flush_task:
            self.flush_task.cancel()
            try:
                await self.flush_task
            except asyncio.CancelledError:
                pass
        await self.flush()
        logger.info("Telemetry collector stopped")
        
    async def _auto_flush(self):
        """Automatically flush buffer every 5 seconds."""
        while True:
            try:
                await asyncio.sleep(5)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto-flush: {e}")
                
    async def flush(self):
        """Flush buffered events to database."""
        if not self.buffer:
            return
            
        events_to_flush = self.buffer.copy()
        self.buffer.clear()
        
        try:
            await self._write_events_batch(events_to_flush)
            logger.debug(f"Flushed {len(events_to_flush)} telemetry events")
        except Exception as e:
            logger.error(f"Error flushing telemetry: {e}")
            # Re-add to buffer for retry
            self.buffer.extend(events_to_flush)
            
    async def _write_events_batch(self, events: List[Dict[str, Any]]):
        """Write a batch of events to database."""
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                for event in events:
                    await self._write_event(conn, event)
                    
    async def _write_event(self, conn: asyncpg.Connection, event: Dict[str, Any]):
        """Write a single event to database."""
        event_id = uuid.uuid4()
        
        # Insert main telemetry event
        await conn.execute("""
            INSERT INTO telemetry_events (
                event_id, timestamp, session_id, event_type, event_category,
                agent_name, workflow_id, step_name, event_name, status,
                duration_ms, token_count, input_data, output_data, error_data,
                metadata, trace_id, span_id, parent_span_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
        """,
            event_id,
            event.get("timestamp", datetime.utcnow()),
            event.get("session_id"),
            event.get("event_type"),
            event.get("event_category"),
            event.get("agent_name"),
            event.get("workflow_id"),
            event.get("step_name"),
            event.get("event_name"),
            event.get("status"),
            event.get("duration_ms"),
            event.get("token_count"),
            json.dumps(event.get("input_data")) if event.get("input_data") else None,
            json.dumps(event.get("output_data")) if event.get("output_data") else None,
            json.dumps(event.get("error_data")) if event.get("error_data") else None,
            json.dumps(event.get("metadata")) if event.get("metadata") else None,
            event.get("trace_id"),
            event.get("span_id"),
            event.get("parent_span_id"),
        )
        
        # Insert type-specific metrics
        if event.get("event_category") == "agent":
            await self._write_agent_metrics(conn, event_id, event)
        elif event.get("event_category") == "tool":
            await self._write_tool_metrics(conn, event_id, event)
        elif event.get("event_category") == "workflow":
            await self._write_workflow_metrics(conn, event_id, event)
        elif event.get("event_category") == "request":
            await self._write_request_metrics(conn, event_id, event)
        elif event.get("event_category") == "error":
            await self._write_error_log(conn, event_id, event)
            
    async def _write_agent_metrics(self, conn: asyncpg.Connection, event_id: uuid.UUID, event: Dict[str, Any]):
        """Write agent-specific metrics."""
        await conn.execute("""
            INSERT INTO agent_metrics (
                event_id, timestamp, session_id, agent_name, execution_status,
                execution_time_ms, prompt_tokens, completion_tokens, total_tokens,
                model_name, temperature, tools_called, tool_names, decision_type,
                confidence_score, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        """,
            event_id,
            event.get("timestamp", datetime.utcnow()),
            event.get("session_id"),
            event.get("agent_name"),
            event.get("execution_status"),
            event.get("duration_ms") or event.get("execution_time_ms"),  # Support both names
            event.get("prompt_tokens"),
            event.get("completion_tokens"),
            event.get("token_count") or event.get("total_tokens"),  # Support both names
            event.get("model_name"),
            event.get("temperature"),
            event.get("tools_called", 0),
            event.get("tool_names", []),
            event.get("decision_type"),
            event.get("confidence_score"),
            json.dumps(event.get("metadata")) if event.get("metadata") else None,
        )
        
    async def _write_tool_metrics(self, conn: asyncpg.Connection, event_id: uuid.UUID, event: Dict[str, Any]):
        """Write tool-specific metrics."""
        await conn.execute("""
            INSERT INTO tool_metrics (
                event_id, timestamp, session_id, tool_name, tool_server,
                status, execution_time_ms, arguments, result, error_message,
                circuit_state, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """,
            event_id,
            event.get("timestamp", datetime.utcnow()),
            event.get("session_id"),
            event.get("tool_name"),
            event.get("tool_server"),
            event.get("status"),
            event.get("duration_ms") or event.get("execution_time_ms"),  # Support both names
            json.dumps(event.get("arguments")) if event.get("arguments") else None,
            json.dumps(event.get("result")) if event.get("result") else None,
            event.get("error_message"),
            event.get("circuit_state"),
            json.dumps(event.get("metadata")) if event.get("metadata") else None,
        )
        
    async def _write_workflow_metrics(self, conn: asyncpg.Connection, event_id: uuid.UUID, event: Dict[str, Any]):
        """Write workflow-specific metrics."""
        await conn.execute("""
            INSERT INTO workflow_metrics (
                event_id, timestamp, session_id, workflow_id, workflow_status,
                current_step, total_steps, completed_steps, started_at,
                completed_at, duration_ms, data_collected, user_interactions,
                requests_sent, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        """,
            event_id,
            event.get("timestamp", datetime.utcnow()),
            event.get("session_id"),
            event.get("workflow_id"),
            event.get("workflow_status"),
            event.get("current_step"),
            event.get("total_steps"),
            event.get("completed_steps"),
            event.get("started_at"),
            event.get("completed_at"),
            event.get("duration_ms"),
            json.dumps(event.get("data_collected")) if event.get("data_collected") else None,
            event.get("user_interactions", 0),
            event.get("requests_sent", 0),
            json.dumps(event.get("metadata")) if event.get("metadata") else None,
        )
        
    async def _write_request_metrics(self, conn: asyncpg.Connection, event_id: uuid.UUID, event: Dict[str, Any]):
        """Write request-specific metrics."""
        await conn.execute("""
            INSERT INTO request_metrics (
                event_id, timestamp, session_id, request_id, request_type,
                prompt, step_name, response_received, response_time_ms,
                user_response, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """,
            event_id,
            event.get("timestamp", datetime.utcnow()),
            event.get("session_id"),
            event.get("request_id"),
            event.get("request_type"),
            event.get("prompt"),
            event.get("step_name"),
            event.get("response_received", False),
            event.get("response_time_ms"),
            event.get("user_response"),
            json.dumps(event.get("metadata")) if event.get("metadata") else None,
        )
        
    async def _write_error_log(self, conn: asyncpg.Connection, event_id: uuid.UUID, event: Dict[str, Any]):
        """Write error log."""
        await conn.execute("""
            INSERT INTO error_logs (
                event_id, timestamp, session_id, error_type, error_message,
                error_stack, component, operation, severity, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
            event_id,
            event.get("timestamp", datetime.utcnow()),
            event.get("session_id"),
            event.get("error_type"),
            event.get("error_message"),
            event.get("error_stack"),
            event.get("component"),
            event.get("operation"),
            event.get("severity", "error"),
            json.dumps(event.get("metadata")) if event.get("metadata") else None,
        )
        
    # Public methods for logging events
    
    def _enrich_event_with_trace_context(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Add OpenTelemetry trace context and span attributes to event if available."""
        if OTEL_AVAILABLE:
            current_span = trace.get_current_span()
            if current_span and current_span.get_span_context().is_valid:
                span_context = current_span.get_span_context()
                event['trace_id'] = format(span_context.trace_id, '032x')
                event['span_id'] = format(span_context.span_id, '016x')
                
                # Capture span attributes (gen_ai.* attributes from Agent Framework)
                try:
                    # Get span attributes if available
                    if hasattr(current_span, 'attributes') and current_span.attributes:
                        span_attrs = dict(current_span.attributes)
                        
                        # Extract relevant attributes for telemetry
                        metadata = event.get('metadata', {})
                        if isinstance(metadata, str):
                            import json
                            metadata = json.loads(metadata)
                        
                        # Add OpenTelemetry gen_ai attributes
                        if 'gen_ai.operation.name' in span_attrs:
                            metadata['operation'] = span_attrs['gen_ai.operation.name']
                        if 'gen_ai.system' in span_attrs:
                            metadata['ai_system'] = span_attrs['gen_ai.system']
                        if 'gen_ai.agent.id' in span_attrs:
                            metadata['agent_id'] = span_attrs['gen_ai.agent.id']
                        if 'gen_ai.request.instructions' in span_attrs:
                            metadata['instructions'] = span_attrs['gen_ai.request.instructions']
                        if 'gen_ai.response.id' in span_attrs:
                            metadata['response_id'] = span_attrs['gen_ai.response.id']
                        if 'gen_ai.usage.input_tokens' in span_attrs:
                            event['prompt_tokens'] = span_attrs['gen_ai.usage.input_tokens']
                        if 'gen_ai.usage.output_tokens' in span_attrs:
                            event['completion_tokens'] = span_attrs['gen_ai.usage.output_tokens']
                        # Compute total tokens from span attributes if not already set
                        if event.get('token_count') is None:
                            pt = event.get('prompt_tokens')
                            ct = event.get('completion_tokens')
                            if pt is not None or ct is not None:
                                try:
                                    event['token_count'] = int(pt or 0) + int(ct or 0)
                                except Exception:
                                    pass
                        
                        # Store all span attributes in metadata for debugging
                        metadata['span_attributes'] = {
                            k: v for k, v in span_attrs.items() 
                            if k.startswith('gen_ai.') or k.startswith('http.') or k.startswith('db.')
                        }
                        
                        event['metadata'] = metadata
                except Exception as e:
                    logger.warning(f"Failed to capture span attributes: {e}")

                # Fallback: if tokens not present, try usage cache for this trace
                try:
                    if (event.get('prompt_tokens') is None and event.get('completion_tokens') is None) or event.get('token_count') is None:
                        usage = get_trace_usage(event.get('trace_id')) if event.get('trace_id') else None
                        if usage:
                            if event.get('prompt_tokens') is None:
                                event['prompt_tokens'] = usage.get('prompt_tokens')
                            if event.get('completion_tokens') is None:
                                event['completion_tokens'] = usage.get('completion_tokens')
                            if event.get('token_count') is None:
                                event['token_count'] = usage.get('total_tokens')
                except Exception:
                    pass
        
        return event
    
    def log_agent_event(
        self,
        session_id: str,
        agent_name: str,
        event_name: str,
        status: str,
        duration_ms: Optional[int] = None,
        tokens: Optional[int] = None,
        decision_type: Optional[str] = None,
        tools_called: Optional[List[str]] = None,
        **kwargs
    ):
        """Log an agent execution event."""
        event = {
            "timestamp": datetime.utcnow(),
            "session_id": session_id,
            "event_type": "agent_call",
            "event_category": "agent",
            "agent_name": agent_name,
            "event_name": event_name,
            "status": status,
            "duration_ms": duration_ms,
            "token_count": tokens,
            "execution_status": status,
            "decision_type": decision_type,
            "tools_called": len(tools_called) if tools_called else 0,
            "tool_names": tools_called,
            **kwargs
        }
        # If explicit total tokens not provided, derive from prompt/completion if available
        if event.get("token_count") is None:
            pt = event.get("prompt_tokens")
            ct = event.get("completion_tokens")
            if pt is not None or ct is not None:
                try:
                    event["token_count"] = int(pt or 0) + int(ct or 0)
                except Exception:
                    pass
        event = self._enrich_event_with_trace_context(event)
        self.buffer.append(event)
        
        if len(self.buffer) >= self.buffer_size:
            asyncio.create_task(self.flush())
            
    def log_tool_event(
        self,
        session_id: str,
        tool_name: str,
        tool_server: str,
        status: str,
        duration_ms: Optional[int] = None,
        arguments: Optional[Dict] = None,
        result: Optional[Dict] = None,
        error_message: Optional[str] = None,
        **kwargs
    ):
        """Log a tool invocation event."""
        event = {
            "timestamp": datetime.utcnow(),
            "session_id": session_id,
            "event_type": "tool_call",
            "event_category": "tool",
            "tool_name": tool_name,
            "tool_server": tool_server,
            "event_name": f"tool:{tool_name}",
            "status": status,
            "duration_ms": duration_ms,
            "arguments": arguments,
            "result": result,
            "error_message": error_message,
            **kwargs
        }
        event = self._enrich_event_with_trace_context(event)
        self.buffer.append(event)
        
        if len(self.buffer) >= self.buffer_size:
            asyncio.create_task(self.flush())
            
    def log_workflow_event(
        self,
        session_id: str,
        workflow_id: str,
        workflow_status: str,
        current_step: Optional[str] = None,
        total_steps: Optional[int] = None,
        completed_steps: Optional[int] = None,
        data_collected: Optional[Dict] = None,
        **kwargs
    ):
        """Log a workflow event."""
        event = {
            "timestamp": datetime.utcnow(),
            "session_id": session_id,
            "event_type": "workflow_step",
            "event_category": "workflow",
            "workflow_id": workflow_id,
            "event_name": f"workflow:{workflow_status}",
            "status": workflow_status,
            "workflow_status": workflow_status,
            "current_step": current_step,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "data_collected": data_collected,
            **kwargs
        }
        event = self._enrich_event_with_trace_context(event)
        self.buffer.append(event)
        
        if len(self.buffer) >= self.buffer_size:
            asyncio.create_task(self.flush())
            
    def log_request_event(
        self,
        session_id: str,
        request_id: str,
        request_type: str,
        prompt: str,
        step_name: str,
        response_received: bool = False,
        user_response: Optional[str] = None,
        **kwargs
    ):
        """Log a request/response event."""
        # Determine status based on response received
        status = "completed" if response_received else "pending"
        
        event = {
            "timestamp": datetime.utcnow(),
            "session_id": session_id,
            "event_type": "request_info",
            "event_category": "request",
            "event_name": f"request:{request_type}",
            "status": status,
            "request_id": request_id,
            "request_type": request_type,
            "prompt": prompt,
            "step_name": step_name,
            "response_received": response_received,
            "user_response": user_response,
            **kwargs
        }
        event = self._enrich_event_with_trace_context(event)
        self.buffer.append(event)
        
        if len(self.buffer) >= self.buffer_size:
            asyncio.create_task(self.flush())
            
    def log_error(
        self,
        session_id: Optional[str],
        error_type: str,
        error_message: str,
        component: str,
        operation: str,
        severity: str = "error",
        error_stack: Optional[str] = None,
        **kwargs
    ):
        """Log an error event."""
        event = {
            "timestamp": datetime.utcnow(),
            "session_id": session_id,
            "event_type": "error",
            "event_category": "error",
            "event_name": f"error:{error_type}",
            "error_type": error_type,
            "error_message": error_message,
            "error_stack": error_stack,
            "component": component,
            "operation": operation,
            "severity": severity,
            **kwargs
        }
        event = self._enrich_event_with_trace_context(event)
        self.buffer.append(event)
        
        if len(self.buffer) >= self.buffer_size:
            asyncio.create_task(self.flush())


# Global telemetry collector instance
_collector: Optional[TelemetryCollector] = None


def get_telemetry_collector() -> Optional[TelemetryCollector]:
    """Get the global telemetry collector instance."""
    return _collector


def set_telemetry_collector(collector: TelemetryCollector):
    """Set the global telemetry collector instance."""
    global _collector
    _collector = collector


async def get_recent_telemetry(
    db_pool: asyncpg.Pool,
    session_id: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get recent telemetry events."""
    async with db_pool.acquire() as conn:
        if session_id:
            rows = await conn.fetch("""
                SELECT * FROM v_recent_telemetry
                WHERE session_id = $1
                ORDER BY timestamp DESC
                LIMIT $2
            """, session_id, limit)
        else:
            rows = await conn.fetch("""
                SELECT * FROM v_recent_telemetry
                ORDER BY timestamp DESC
                LIMIT $1
            """, limit)
            
        return [dict(row) for row in rows]


async def get_session_telemetry_stream(
    db_pool: asyncpg.Pool,
    session_id: str
):
    """Stream telemetry events for a session (for SSE)."""
    last_timestamp = datetime.utcnow()
    
    while True:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    event_id, timestamp, event_type, event_name,
                    agent_name, status, duration_ms, step_name
                FROM telemetry_events
                WHERE session_id = $1 AND timestamp > $2
                ORDER BY timestamp ASC
            """, session_id, last_timestamp)
            
            for row in rows:
                yield dict(row)
                last_timestamp = row['timestamp']
                
        await asyncio.sleep(1)  # Poll every second
