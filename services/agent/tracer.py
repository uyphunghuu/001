"""Agent Execution Tracer — tracks every step of agent execution.

Tracks:
    - Tool calls: name, arguments, result, latency, success/failure, retries
    - Memory operations: store, retrieve, compress, conflict detection
    - Planning: steps generated, steps completed, loops, dead ends
    - Execution: per-step latency, token usage, cost, error recovery
    - Provenance: source attribution for every claim in the response

Why tracing matters:
    - Without traces, debugging agent failures is impossible
    - Without provenance, you can't trust agent responses
    - Without cost tracking, LLM costs explode unnoticed
    - Without retry tracking, silent failures cascade
"""
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from data.observability import metrics, logger


class ToolCallStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRYING = "retrying"


@dataclass
class ToolCall:
    id: str
    tool_name: str
    arguments: dict
    result: Optional[str] = None
    status: ToolCallStatus = ToolCallStatus.SUCCESS
    latency_ms: float = 0.0
    retry_count: int = 0
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    argument_size: int = 0
    result_size: int = 0
    timestamp: str = ""


@dataclass
class MemoryEntry:
    id: str
    memory_type: str  # "episodic", "semantic", "procedural"
    content: str
    context: dict = field(default_factory=dict)
    access_count: int = 0
    created_at: str = ""
    last_accessed: str = ""
    conflict_with: Optional[str] = None  # ID of contradicting memory


@dataclass
class PlanStep:
    id: str
    description: str
    status: str  # "pending", "in_progress", "completed", "failed", "skipped"
    tool_calls: list[ToolCall] = field(default_factory=list)
    latency_ms: float = 0.0
    error: Optional[str] = None
    started_at: str = ""
    completed_at: str = ""


@dataclass
class AgentTrace:
    id: str
    session_id: str
    query: str
    response: Optional[str] = None
    steps: list[PlanStep] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    memories_accessed: list[MemoryEntry] = field(default_factory=list)
    total_latency_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    hallucination_score: float = 0.0
    provenance: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    created_at: str = ""


class AgentTracer:
    """Records every step of agent execution for observability and debugging.

    Usage:
        tracer = AgentTracer(session_id="session_123")
        trace = tracer.start_trace("What is the capital of France?")

        # Record a tool call
        tool = tracer.record_tool_call(trace.id, "search_web", {"query": "capital of France"})
        # ... execute tool ...
        tracer.complete_tool_call(tool.id, result="Paris", latency_ms=250, success=True)

        # Record a plan step
        step = tracer.record_plan_step(trace.id, "Search for capital of France")
        tracer.complete_plan_step(step.id)

        # Record memory access
        tracer.record_memory_access(trace.id, "semantic", "France capital is Paris")

        # Complete the trace
        tracer.complete_trace(trace.id, response="The capital of France is Paris.")

        # Get full trace for storage
        trace = tracer.get_trace(trace.id)
    """

    def __init__(self, session_id: str = ""):
        self.session_id = session_id or str(uuid.uuid4())
        self._traces: dict[str, AgentTrace] = {}
        self._tool_calls: dict[str, ToolCall] = {}
        self._plan_steps: dict[str, PlanStep] = {}

    def start_trace(self, query: str) -> AgentTrace:
        """Start a new agent execution trace."""
        trace = AgentTrace(
            id=str(uuid.uuid4()),
            session_id=self.session_id,
            query=query,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._traces[trace.id] = trace

        logger.info("Agent trace started", component="agent_tracer", event="trace.start",
                     trace_id=trace.id, session_id=self.session_id, query=query[:100])

        metrics.counter("agent_traces_started", tags={"session": self.session_id}).inc()

        return trace

    def complete_trace(self, trace_id: str, response: str = "", error: Optional[str] = None):
        """Complete an agent execution trace."""
        trace = self._traces.get(trace_id)
        if not trace:
            return

        trace.response = response
        trace.error = error

        # Calculate total metrics
        total_latency = sum(s.latency_ms for s in trace.steps)
        for tc in trace.tool_calls:
            trace.total_input_tokens += tc.input_tokens
            trace.total_output_tokens += tc.output_tokens

        trace.total_latency_ms = total_latency
        trace.total_cost_usd = sum(tc.cost_usd for tc in trace.tool_calls)

        # Record metrics
        metrics.histogram("agent_trace_latency_ms").observe(total_latency)
        metrics.gauge("agent_trace_total_tokens").set(trace.total_input_tokens + trace.total_output_tokens)
        metrics.gauge("agent_trace_cost_usd").set(trace.total_cost_usd)
        metrics.counter("agent_traces_completed").inc()

        logger.info("Agent trace completed", component="agent_tracer", event="trace.complete",
                     trace_id=trace_id, latency_ms=total_latency, steps=len(trace.steps),
                     tool_calls=len(trace.tool_calls), tokens=trace.total_input_tokens + trace.total_output_tokens,
                     cost=trace.total_cost_usd)

    def record_tool_call(self, trace_id: str, tool_name: str, arguments: dict) -> ToolCall:
        """Record a tool call."""
        tc = ToolCall(
            id=str(uuid.uuid4()),
            tool_name=tool_name,
            arguments=arguments,
            argument_size=len(str(arguments)),
            status=ToolCallStatus.RETRYING,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._tool_calls[tc.id] = tc

        trace = self._traces.get(trace_id)
        if trace:
            trace.tool_calls.append(tc)

        metrics.counter("agent_tool_calls", tags={"tool": tool_name}).inc()

        return tc

    def complete_tool_call(self, tool_call_id: str, result: str, latency_ms: float,
                            success: bool = True, error: str = "", input_tokens: int = 0,
                            output_tokens: int = 0, cost_usd: float = 0.0):
        """Complete a tool call with results and metrics."""
        tc = self._tool_calls.get(tool_call_id)
        if not tc:
            return

        tc.result = result
        tc.latency_ms = latency_ms
        tc.status = ToolCallStatus.SUCCESS if success else ToolCallStatus.FAILED
        tc.error = error
        tc.input_tokens = input_tokens
        tc.output_tokens = output_tokens
        tc.cost_usd = cost_usd
        tc.result_size = len(result)

        tags = {"tool": tc.tool_name, "status": tc.status.value}
        metrics.histogram("agent_tool_latency_ms", tags=tags).observe(latency_ms)
        metrics.histogram("agent_tool_argument_size", tags=tags).observe(tc.argument_size)
        metrics.histogram("agent_tool_result_size", tags=tags).observe(tc.result_size)
        if not success:
            metrics.counter("agent_tool_failures", tags={"tool": tc.tool_name}).inc()
            logger.error("Tool call failed", component="agent_tracer", event="tool.failed",
                         tool=tc.tool_name, error=error, latency_ms=latency_ms)

    def record_tool_retry(self, tool_call_id: str):
        """Increment retry count for a tool call."""
        tc = self._tool_calls.get(tool_call_id)
        if tc:
            tc.retry_count += 1
            tc.status = ToolCallStatus.RETRYING
            metrics.counter("agent_tool_retries", tags={"tool": tc.tool_name}).inc()

    def record_plan_step(self, trace_id: str, description: str) -> PlanStep:
        """Record a planning step."""
        step = PlanStep(
            id=str(uuid.uuid4()),
            description=description,
            status="pending",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._plan_steps[step.id] = step

        trace = self._traces.get(trace_id)
        if trace:
            trace.steps.append(step)

        metrics.counter("agent_plan_steps", tags={"status": "created"}).inc()

        return step

    def complete_plan_step(self, step_id: str, status: str = "completed", error: Optional[str] = None):
        """Complete a planning step with timing."""
        step = self._plan_steps.get(step_id)
        if not step:
            return

        step.status = status
        step.completed_at = datetime.now(timezone.utc).isoformat()
        step.latency_ms = self._calc_latency_ms(step.started_at, step.completed_at)
        step.error = error

        metrics.histogram("agent_plan_step_latency_ms").observe(step.latency_ms)
        metrics.counter("agent_plan_steps", tags={"status": status}).inc()

    def record_memory_access(self, trace_id: str, memory_type: str, content: str,
                              context: dict = None) -> MemoryEntry:
        """Record a memory access during agent execution."""
        mem = MemoryEntry(
            id=str(uuid.uuid4()),
            memory_type=memory_type,
            content=content[:500],
            context=context or {},
            access_count=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            last_accessed=datetime.now(timezone.utc).isoformat(),
        )

        trace = self._traces.get(trace_id)
        if trace:
            trace.memories_accessed.append(mem)

        metrics.counter("agent_memory_access", tags={"type": memory_type}).inc()

        return mem

    def record_provenance(self, trace_id: str, claim: str, source_node_id: str,
                           source_content: str, confidence: float = 1.0):
        """Record provenance: which source supports which claim."""
        trace = self._traces.get(trace_id)
        if trace:
            trace.provenance.append({
                "claim": claim[:200],
                "source_node_id": source_node_id,
                "source_content_snippet": source_content[:200],
                "confidence": confidence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            metrics.counter("agent_provenance_entries").inc()

    def get_trace(self, trace_id: str) -> Optional[AgentTrace]:
        """Get a complete trace by ID."""
        return self._traces.get(trace_id)

    def get_session_traces(self, session_id: str) -> list[AgentTrace]:
        """Get all traces for a session."""
        return [t for t in self._traces.values() if t.session_id == session_id]

    def _calc_latency_ms(self, start_str: str, end_str: str) -> float:
        try:
            start = datetime.fromisoformat(start_str)
            end = datetime.fromisoformat(end_str)
            return (end - start).total_seconds() * 1000
        except Exception:
            return 0.0
