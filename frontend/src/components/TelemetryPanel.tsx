import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Paper,
  Typography,
  Chip,
  IconButton,
  Collapse,
  List,
  ListItem,
  ListItemText,
  Divider,
  CircularProgress,
  Tooltip,
  Grid,
  Card,
  CardContent,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Refresh as RefreshIcon,
  Timeline as TimelineIcon,
  Error as ErrorIcon,
  CheckCircle as CheckCircleIcon,
  Settings as SettingsIcon,
} from '@mui/icons-material';

interface TelemetryEvent {
  event_id: string;
  timestamp: string;
  event_type: string;
  event_name: string;
  agent_name?: string;
  tool_name?: string;
  status?: string;
  duration_ms?: number;
  step_name?: string;
  total_tokens?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  trace_id?: string;
  span_id?: string;
  metadata?: {
    operation?: string;
    ai_system?: string;
    agent_id?: string;
    instructions?: string;
    response_id?: string;
    span_attributes?: Record<string, any>;
  };
}

interface TelemetryStats {
  summary: {
    total_events: number;
    agents_used: number;
    total_duration_ms: number;
    errors: number;
    started_at?: string;
    last_activity?: string;
  };
  agents: Array<{
    agent_name: string;
    calls: number;
    avg_duration_ms: number;
    total_tokens: number;
  }>;
  tools: Array<{
    tool_name: string;
    tool_server: string;
    calls: number;
    avg_duration_ms: number;
    successes: number;
    errors: number;
  }>;
}

interface TelemetryPanelProps {
  sessionId: string | null;
}

const TelemetryPanel: React.FC<TelemetryPanelProps> = ({ sessionId }) => {
  const [expanded, setExpanded] = useState(false);
  const [events, setEvents] = useState<TelemetryEvent[]>([]);
  const [stats, setStats] = useState<TelemetryStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const eventSourceRef = useRef<EventSource | null>(null);

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  // Fetch telemetry events
  const fetchTelemetryEvents = async () => {
    if (!sessionId) return;

    try {
      setLoading(true);
      const response = await fetch(`${apiBaseUrl}/telemetry/session/${sessionId}`);
      if (!response.ok) throw new Error('Failed to fetch telemetry');
      
      const data = await response.json();
      setEvents(data.events || []);
      setError(null);
    } catch (err) {
      console.error('Error fetching telemetry:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch telemetry');
    } finally {
      setLoading(false);
    }
  };

  // Fetch telemetry stats
  const fetchTelemetryStats = async () => {
    if (!sessionId) return;

    try {
      const response = await fetch(`${apiBaseUrl}/telemetry/stats/${sessionId}`);
      if (!response.ok) throw new Error('Failed to fetch stats');
      
      const data = await response.json();
      setStats(data);
    } catch (err) {
      console.error('Error fetching stats:', err);
    }
  };

  // Setup SSE stream for real-time updates
  useEffect(() => {
    if (!sessionId || !autoRefresh || !expanded) return;

    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    // Setup new SSE connection
    const eventSource = new EventSource(`${apiBaseUrl}/telemetry/stream/${sessionId}`);
    
    eventSource.onmessage = (event) => {
      try {
        const newEvent = JSON.parse(event.data);
        setEvents((prev) => [newEvent, ...prev].slice(0, 100)); // Keep last 100 events
      } catch (err) {
        console.error('Error parsing telemetry event:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE error:', err);
      eventSource.close();
    };

    eventSourceRef.current = eventSource;

    return () => {
      eventSource.close();
    };
  }, [sessionId, autoRefresh, expanded, apiBaseUrl]);

  // Initial fetch
  useEffect(() => {
    if (sessionId && expanded) {
      fetchTelemetryEvents();
      fetchTelemetryStats();
    }
  }, [sessionId, expanded]);

  // Auto-refresh stats every 5 seconds
  useEffect(() => {
    if (!sessionId || !autoRefresh || !expanded) return;

    const interval = setInterval(() => {
      fetchTelemetryStats();
    }, 5000);

    return () => clearInterval(interval);
  }, [sessionId, autoRefresh, expanded]);

  const getStatusColor = (status?: string) => {
    switch (status) {
      case 'success':
      case 'completed':
        return 'success';
      case 'failed':
      case 'error':
        return 'error';
      case 'pending':
      case 'in_progress':
        return 'warning';
      default:
        return 'default';
    }
  };

  const getEventIcon = (eventType: string, status?: string) => {
    if (status === 'failed' || status === 'error') {
      return <ErrorIcon fontSize="small" color="error" />;
    }
    if (status === 'success' || status === 'completed') {
      return <CheckCircleIcon fontSize="small" color="success" />;
    }
    return <SettingsIcon fontSize="small" />;
  };

  const formatDuration = (ms?: number) => {
    if (!ms) return 'N/A';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const formatTimestamp = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString();
    } catch {
      return timestamp;
    }
  };

  if (!sessionId) {
    return null;
  }

  return (
    <Paper
      elevation={3}
      sx={{
        position: 'fixed',
        bottom: 16,
        right: 16,
        width: expanded ? 500 : 60,
        maxHeight: expanded ? '60vh' : 60,
        transition: 'all 0.3s ease',
        zIndex: 1000,
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <Box
        sx={{
          p: 1.5,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          bgcolor: 'primary.main',
          color: 'white',
          cursor: 'pointer',
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <TimelineIcon />
          {expanded && <Typography variant="subtitle2">Telemetry</Typography>}
        </Box>
        <IconButton size="small" sx={{ color: 'white' }}>
          {expanded ? <ExpandMoreIcon /> : <ExpandLessIcon />}
        </IconButton>
      </Box>

      <Collapse in={expanded}>
        <Box sx={{ maxHeight: 'calc(60vh - 60px)', overflow: 'auto' }}>
          {loading && (
            <Box sx={{ p: 2, textAlign: 'center' }}>
              <CircularProgress size={24} />
            </Box>
          )}

          {error && (
            <Box sx={{ p: 2 }}>
              <Typography color="error" variant="body2">
                {error}
              </Typography>
            </Box>
          )}

          {/* Stats Summary */}
          {stats && (
            <Box sx={{ p: 2, bgcolor: 'grey.50' }}>
              <Grid container spacing={1}>
                <Grid item xs={6}>
                  <Card variant="outlined">
                    <CardContent sx={{ p: 1, '&:last-child': { pb: 1 } }}>
                      <Typography variant="caption" color="text.secondary">
                        Events
                      </Typography>
                      <Typography variant="h6">
                        {stats.summary.total_events || 0}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={6}>
                  <Card variant="outlined">
                    <CardContent sx={{ p: 1, '&:last-child': { pb: 1 } }}>
                      <Typography variant="caption" color="text.secondary">
                        Errors
                      </Typography>
                      <Typography variant="h6" color={stats.summary.errors > 0 ? 'error' : 'inherit'}>
                        {stats.summary.errors || 0}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={6}>
                  <Card variant="outlined">
                    <CardContent sx={{ p: 1, '&:last-child': { pb: 1 } }}>
                      <Typography variant="caption" color="text.secondary">
                        Agents
                      </Typography>
                      <Typography variant="h6">
                        {stats.summary.agents_used || 0}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={6}>
                  <Card variant="outlined">
                    <CardContent sx={{ p: 1, '&:last-child': { pb: 1 } }}>
                      <Typography variant="caption" color="text.secondary">
                        Duration
                      </Typography>
                      <Typography variant="h6">
                        {formatDuration(stats.summary.total_duration_ms)}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>

              <Box sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                {stats.agents.map((agent) => (
                  <Tooltip
                    key={agent.agent_name}
                    title={`${agent.calls} calls, ${formatDuration(agent.avg_duration_ms)} avg, ${agent.total_tokens} tokens`}
                  >
                    <Chip
                      label={agent.agent_name}
                      size="small"
                      variant="outlined"
                      color="primary"
                    />
                  </Tooltip>
                ))}
              </Box>
            </Box>
          )}

          <Divider />

          {/* Controls */}
          <Box sx={{ p: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="caption" color="text.secondary">
              Recent Events
            </Typography>
            <Tooltip title="Refresh">
              <IconButton size="small" onClick={fetchTelemetryEvents}>
                <RefreshIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>

          <Divider />

          {/* Events List */}
          <List dense sx={{ p: 0 }}>
            {events.slice(0, 20).map((event, index) => (
              <React.Fragment key={event.event_id || index}>
                <ListItem>
                  <Box sx={{ width: '100%' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                      {getEventIcon(event.event_type, event.status)}
                      <Typography variant="body2" sx={{ fontWeight: 500, flex: 1 }}>
                        {event.agent_name || event.tool_name || event.event_name}
                      </Typography>
                      <Chip
                        label={event.status || 'N/A'}
                        size="small"
                        color={getStatusColor(event.status)}
                        sx={{ height: 20 }}
                      />
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="caption" color="text.secondary">
                        {formatTimestamp(event.timestamp)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {formatDuration(event.duration_ms)}
                        {event.total_tokens && ` • ${event.total_tokens} tokens`}
                      </Typography>
                    </Box>
                    
                    {/* OpenTelemetry Details */}
                    {(event.metadata || event.prompt_tokens || event.trace_id) && (
                      <Box sx={{ mt: 1, p: 1, bgcolor: 'grey.50', borderRadius: 1 }}>
                        {/* Token Usage */}
                        {(event.prompt_tokens || event.completion_tokens) && (
                          <Typography variant="caption" display="block" sx={{ mb: 0.5 }}>
                            <strong>Tokens:</strong> {event.prompt_tokens || 0} in / {event.completion_tokens || 0} out
                          </Typography>
                        )}
                        
                        {/* AI Operation */}
                        {event.metadata?.operation && (
                          <Typography variant="caption" display="block" sx={{ mb: 0.5 }}>
                            <strong>Operation:</strong> {event.metadata.operation}
                          </Typography>
                        )}
                        
                        {/* AI System */}
                        {event.metadata?.ai_system && (
                          <Typography variant="caption" display="block" sx={{ mb: 0.5 }}>
                            <strong>System:</strong> {event.metadata.ai_system}
                          </Typography>
                        )}
                        
                        {/* Agent ID */}
                        {event.metadata?.agent_id && (
                          <Typography variant="caption" display="block" sx={{ mb: 0.5 }}>
                            <strong>Agent ID:</strong> {event.metadata.agent_id}
                          </Typography>
                        )}
                        
                        {/* Response ID */}
                        {event.metadata?.response_id && (
                          <Typography variant="caption" display="block" sx={{ mb: 0.5 }}>
                            <strong>Response ID:</strong> {event.metadata.response_id}
                          </Typography>
                        )}
                        
                        {/* Instructions (truncated) */}
                        {event.metadata?.instructions && (
                          <Typography variant="caption" display="block" sx={{ mb: 0.5 }}>
                            <strong>Instructions:</strong> {event.metadata.instructions.substring(0, 100)}{event.metadata.instructions.length > 100 ? '...' : ''}
                          </Typography>
                        )}
                        
                        {/* Trace Context */}
                        {event.trace_id && (
                          <Typography variant="caption" display="block" sx={{ fontFamily: 'monospace', fontSize: '0.65rem' }}>
                            <strong>Trace:</strong> {event.trace_id}:{event.span_id}
                          </Typography>
                        )}
                      </Box>
                    )}
                  </Box>
                </ListItem>
                {index < events.length - 1 && <Divider />}
              </React.Fragment>
            ))}
          </List>

          {events.length === 0 && !loading && (
            <Box sx={{ p: 3, textAlign: 'center' }}>
              <Typography variant="body2" color="text.secondary">
                No telemetry events yet
              </Typography>
            </Box>
          )}
        </Box>
      </Collapse>
    </Paper>
  );
};

export default TelemetryPanel;
