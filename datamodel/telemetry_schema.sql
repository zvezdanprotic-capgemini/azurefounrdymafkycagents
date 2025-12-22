-- Telemetry Schema for MAF Agent Framework Observability
-- Based on Microsoft Agent Framework telemetry patterns

-- Main telemetry events table
CREATE TABLE IF NOT EXISTS telemetry_events (
    id SERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id VARCHAR(255),
    
    -- Event classification
    event_type VARCHAR(50) NOT NULL, -- 'agent_call', 'tool_call', 'workflow_step', 'request_info', 'error'
    event_category VARCHAR(50) NOT NULL, -- 'agent', 'tool', 'workflow', 'system'
    
    -- Agent/Workflow context
    agent_name VARCHAR(100),
    workflow_id VARCHAR(255),
    step_name VARCHAR(100),
    
    -- Event details
    event_name VARCHAR(255) NOT NULL,
    status VARCHAR(50), -- 'started', 'completed', 'failed', 'pending'
    
    -- Performance metrics
    duration_ms INTEGER,
    token_count INTEGER,
    
    -- Data payload
    input_data JSONB,
    output_data JSONB,
    error_data JSONB,
    metadata JSONB,
    
    -- Tracing
    trace_id VARCHAR(255),
    span_id VARCHAR(255),
    parent_span_id VARCHAR(255),
    
    -- Indexing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Agent execution metrics
CREATE TABLE IF NOT EXISTS agent_metrics (
    id SERIAL PRIMARY KEY,
    event_id UUID REFERENCES telemetry_events(event_id),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id VARCHAR(255),
    
    agent_name VARCHAR(100) NOT NULL,
    
    -- Execution details
    execution_status VARCHAR(50), -- 'success', 'failure', 'timeout'
    execution_time_ms INTEGER,
    
    -- Token usage
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    
    -- Model info
    model_name VARCHAR(100),
    temperature DECIMAL(3,2),
    
    -- Tool usage
    tools_called INTEGER DEFAULT 0,
    tool_names TEXT[],
    
    -- Decision tracking
    decision_type VARCHAR(50), -- 'PASS', 'FAIL', 'REVIEW'
    confidence_score DECIMAL(5,4),
    
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tool invocation metrics
CREATE TABLE IF NOT EXISTS tool_metrics (
    id SERIAL PRIMARY KEY,
    event_id UUID REFERENCES telemetry_events(event_id),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id VARCHAR(255),
    
    tool_name VARCHAR(255) NOT NULL,
    tool_server VARCHAR(100), -- 'postgres', 'blob', 'email', 'rag'
    
    -- Execution
    status VARCHAR(50), -- 'success', 'error', 'timeout', 'circuit_open'
    execution_time_ms INTEGER,
    
    -- Request/Response
    arguments JSONB,
    result JSONB,
    error_message TEXT,
    
    -- Circuit breaker state
    circuit_state VARCHAR(50), -- 'closed', 'open', 'half_open'
    
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Workflow execution tracking
CREATE TABLE IF NOT EXISTS workflow_metrics (
    id SERIAL PRIMARY KEY,
    event_id UUID REFERENCES telemetry_events(event_id),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id VARCHAR(255) NOT NULL,
    
    workflow_id VARCHAR(255) NOT NULL,
    workflow_status VARCHAR(50), -- 'started', 'in_progress', 'completed', 'failed', 'paused'
    
    -- Step tracking
    current_step VARCHAR(100),
    total_steps INTEGER,
    completed_steps INTEGER,
    
    -- Timing
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    
    -- Data collection
    data_collected JSONB,
    
    -- HITL metrics
    user_interactions INTEGER DEFAULT 0,
    requests_sent INTEGER DEFAULT 0,
    
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Request/Response tracking (HITL)
CREATE TABLE IF NOT EXISTS request_metrics (
    id SERIAL PRIMARY KEY,
    event_id UUID REFERENCES telemetry_events(event_id),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id VARCHAR(255),
    
    request_id VARCHAR(255) NOT NULL UNIQUE,
    request_type VARCHAR(50), -- 'info_request', 'user_response'
    
    -- Request details
    prompt TEXT,
    step_name VARCHAR(100),
    
    -- Response tracking
    response_received BOOLEAN DEFAULT FALSE,
    response_time_ms INTEGER,
    user_response TEXT,
    
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Error tracking
CREATE TABLE IF NOT EXISTS error_logs (
    id SERIAL PRIMARY KEY,
    event_id UUID REFERENCES telemetry_events(event_id),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id VARCHAR(255),
    
    error_type VARCHAR(100) NOT NULL,
    error_message TEXT,
    error_stack TEXT,
    
    -- Context
    component VARCHAR(100), -- 'agent', 'tool', 'workflow', 'api'
    operation VARCHAR(255),
    
    -- Severity
    severity VARCHAR(20), -- 'info', 'warning', 'error', 'critical'
    
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_telemetry_session ON telemetry_events(session_id, timestamp DESC);
CREATE INDEX idx_telemetry_type ON telemetry_events(event_type, timestamp DESC);
CREATE INDEX idx_telemetry_agent ON telemetry_events(agent_name, timestamp DESC);
CREATE INDEX idx_telemetry_trace ON telemetry_events(trace_id);

CREATE INDEX idx_agent_metrics_session ON agent_metrics(session_id, timestamp DESC);
CREATE INDEX idx_agent_metrics_name ON agent_metrics(agent_name, timestamp DESC);

CREATE INDEX idx_tool_metrics_session ON tool_metrics(session_id, timestamp DESC);
CREATE INDEX idx_tool_metrics_name ON tool_metrics(tool_name, timestamp DESC);
CREATE INDEX idx_tool_metrics_status ON tool_metrics(status, timestamp DESC);

CREATE INDEX idx_workflow_metrics_session ON workflow_metrics(session_id, timestamp DESC);
CREATE INDEX idx_workflow_metrics_status ON workflow_metrics(workflow_status, timestamp DESC);

CREATE INDEX idx_request_metrics_session ON request_metrics(session_id, timestamp DESC);
CREATE INDEX idx_request_metrics_request ON request_metrics(request_id);

CREATE INDEX idx_error_logs_session ON error_logs(session_id, timestamp DESC);
CREATE INDEX idx_error_logs_severity ON error_logs(severity, timestamp DESC);

-- Views for common queries
CREATE OR REPLACE VIEW v_recent_telemetry AS
SELECT 
    te.event_id,
    te.timestamp,
    te.session_id,
    te.event_type,
    te.event_name,
    te.agent_name,
    te.status,
    te.duration_ms,
    am.total_tokens,
    tm.tool_name,
    wm.current_step
FROM telemetry_events te
LEFT JOIN agent_metrics am ON te.event_id = am.event_id
LEFT JOIN tool_metrics tm ON te.event_id = tm.event_id
LEFT JOIN workflow_metrics wm ON te.event_id = wm.event_id
ORDER BY te.timestamp DESC
LIMIT 100;

CREATE OR REPLACE VIEW v_session_summary AS
SELECT 
    session_id,
    COUNT(*) as total_events,
    COUNT(DISTINCT agent_name) as agents_used,
    SUM(duration_ms) as total_duration_ms,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as errors,
    MIN(timestamp) as started_at,
    MAX(timestamp) as last_activity
FROM telemetry_events
GROUP BY session_id;

-- Function to clean old telemetry (optional)
CREATE OR REPLACE FUNCTION cleanup_old_telemetry(days_to_keep INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM telemetry_events 
    WHERE created_at < NOW() - INTERVAL '1 day' * days_to_keep;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions (adjust as needed)
-- GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_app_user;
