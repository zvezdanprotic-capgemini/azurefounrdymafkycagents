#!/bin/bash
# Setup Telemetry Database Schema

set -e

echo "Setting up telemetry database schema..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Database connection details
DB_HOST=${POSTGRES_HOST:-localhost}
DB_PORT=${POSTGRES_PORT:-5432}
DB_NAME=${POSTGRES_DB:-kyc_crm}
DB_USER=${POSTGRES_USER:-postgres}

echo "Connecting to PostgreSQL at $DB_HOST:$DB_PORT/$DB_NAME as $DB_USER"

# Apply telemetry schema
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f datamodel/telemetry_schema.sql

echo "Telemetry schema setup complete!"
echo ""
echo "Available tables:"
echo "- telemetry_events: Main telemetry events"
echo "- agent_metrics: Agent execution metrics"
echo "- tool_metrics: Tool invocation metrics"
echo "- workflow_metrics: Workflow execution tracking"
echo "- request_metrics: Request/response tracking (HITL)"
echo "- error_logs: Error tracking"
echo ""
echo "Available views:"
echo "- v_recent_telemetry: Recent telemetry events with joins"
echo "- v_session_summary: Session-level aggregated statistics"
echo ""
echo "You can now start the application with telemetry enabled!"
