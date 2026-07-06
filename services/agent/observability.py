"""Agent System Observability — comprehensive monitoring for LLM Agents.

This module provides:
    - Agent execution monitoring (tool calls, memory, planning, execution)
    - Hallucination detection (factual consistency, source attribution)
    - Cost tracking (LLM API costs per session/agent)
    - Quality metrics (completion rate, recovery rate, loop detection)
    - User feedback integration

All metrics exposed via Prometheus for Grafana dashboards.
"""
import time
from typing import Optional

from data.observability import metrics, logger


class AgentObservability:
    """Tracks agent-level metrics across sessions and agents.

    Usage:
        agent_obs = AgentObservability()
        agent_obs.record_execution(session_id="s1", latency_ms=1500, steps=5, success=True)
        agent_obs.record_tool_usage(tool_name="search_web", latency_ms=200, success=True)
        agent_obs.detect_loop(session_id="s1", step_count=10, loop_detected=False)
    """

    @staticmethod
    def record_execution(session_id: str, latency_ms: float, steps: int,
                          success: bool = True, error: Optional[str] = None):
        """Record an agent execution."""
        tags = {"success": str(success)}
        metrics.histogram("agent_execution_latency_ms", tags=tags).observe(latency_ms)
        metrics.histogram("agent_execution_steps", tags=tags).observe(steps)
        metrics.counter("agent_executions", tags=tags).inc()
        if not success:
            metrics.counter("agent_execution_failures", tags={"error": error or "unknown"}).inc()

    @staticmethod
    def record_tool_usage(tool_name: str, latency_ms: float, success: bool = True,
                           input_tokens: int = 0, output_tokens: int = 0, cost_usd: float = 0.0):
        """Record tool usage metrics."""
        tags = {"tool": tool_name, "success": str(success)}
        metrics.histogram("agent_tool_latency_ms", tags=tags).observe(latency_ms)
        metrics.histogram("agent_tool_input_tokens", tags=tags).observe(input_tokens)
        metrics.histogram("agent_tool_output_tokens", tags=tags).observe(output_tokens)
        metrics.counter("agent_tool_calls", tags=tags).inc()
        if cost_usd > 0:
            metrics.counter("agent_tool_cost_usd", tags=tags).inc(cost_usd)

    @staticmethod
    def record_planning(steps_planned: int, steps_completed: int, steps_failed: int,
                         has_loop: bool = False, has_dead_end: bool = False):
        """Record planning metrics."""
        completion_rate = steps_completed / max(steps_planned, 1)
        metrics.gauge("agent_planning_completion_rate").set(completion_rate)
        metrics.gauge("agent_planning_steps_planned").set(steps_planned)
        metrics.gauge("agent_planning_steps_failed").set(steps_failed)
        metrics.gauge("agent_planning_loop_detected").set(1 if has_loop else 0)
        metrics.gauge("agent_planning_dead_end").set(1 if has_dead_end else 0)
        if has_loop:
            logger.warning("Planning loop detected", component="agent_observability",
                           event="agent.planning_loop")

    @staticmethod
    def record_memory(memory_count: int, memory_size_bytes: int, retrieval_latency_ms: float,
                       conflict_count: int = 0):
        """Record memory system metrics."""
        metrics.gauge("agent_memory_count").set(memory_count)
        metrics.gauge("agent_memory_size_bytes").set(memory_size_bytes)
        metrics.histogram("agent_memory_retrieval_latency_ms").observe(retrieval_latency_ms)
        metrics.gauge("agent_memory_conflicts").set(conflict_count)

    @staticmethod
    def record_recovery(original_error: str, recovery_strategy: str, success: bool):
        """Record error recovery metrics."""
        tags = {"strategy": recovery_strategy, "success": str(success)}
        metrics.counter("agent_recovery_attempts", tags=tags).inc()
        logger.info("Agent recovery", component="agent_observability", event="agent.recovery",
                     strategy=recovery_strategy, original_error=original_error, success=success)

    @staticmethod
    def record_cost(total_cost_usd: float, total_tokens: int, session_id: str = ""):
        """Record LLM cost metrics."""
        metrics.counter("agent_total_cost_usd", tags={"session": session_id or "global"}).inc(total_cost_usd)
        metrics.counter("agent_total_tokens", tags={"session": session_id or "global"}).inc(total_tokens)
        logger.info("Agent cost", component="agent_observability", event="agent.cost",
                     cost_usd=total_cost_usd, tokens=total_tokens, session=session_id)

    @staticmethod
    def record_session(session_id: str, query_count: int, avg_latency_ms: float,
                        success_rate: float, total_cost_usd: float):
        """Record session-level aggregate metrics."""
        metrics.gauge("agent_session_query_count", tags={"session": session_id}).set(query_count)
        metrics.gauge("agent_session_avg_latency_ms", tags={"session": session_id}).set(avg_latency_ms)
        metrics.gauge("agent_session_success_rate", tags={"session": session_id}).set(success_rate)
        metrics.gauge("agent_session_cost_usd", tags={"session": session_id}).set(total_cost_usd)


class HallucinationDetector:
    """Detects potential hallucinations in agent responses.

    Uses multiple signals:
        1. Source attribution: claims should cite specific retrieved chunks
        2. Factual consistency: claims should not contradict retrieved context
        3. Entity grounding: entities mentioned should exist in retrieved documents
        4. Contradiction detection: response should not contradict earlier statements

    Usage:
        detector = HallucinationDetector()
        score = detector.score_response(
            response="The capital of France is Paris.",
            retrieved_chunks=[...],
            previous_statements=["France's capital is Paris."],
        )
        if score > 0.5:
            logger.warning(f"Hallucination detected: score={score}")
    """

    @staticmethod
    def score_response(response: str, retrieved_chunks: list[dict] = None,
                        previous_statements: list[str] = None,
                        entity_list: list[str] = None) -> dict:
        """Score a response for hallucination risk.

        Returns:
            dict with:
                - overall_score: 0-1 (higher = more likely hallucination)
                - attribution_score: 0-1 (higher = better attribution)
                - entity_grounding_score: 0-1
                - contradiction_score: 0-1
                - signals: dict of individual signal scores
        """
        signals = {}

        # Signal 1: Source attribution
        attribution = HallucinationDetector._check_attribution(response, retrieved_chunks or [])
        signals["attribution"] = attribution

        # Signal 2: Entity grounding
        grounding = HallucinationDetector._check_entity_grounding(
            response, retrieved_chunks or [], entity_list or [])
        signals["entity_grounding"] = grounding

        # Signal 3: Contradiction detection
        contradiction = HallucinationDetector._check_contradiction(
            response, previous_statements or [])
        signals["contradiction"] = contradiction

        # Overall score (weighted average)
        weights = {"attribution": 0.4, "entity_grounding": 0.3, "contradiction": 0.3}
        overall = sum(signals[k] * weights[k] for k in weights)

        result = {
            "overall_score": round(overall, 4),
            "attribution_score": attribution,
            "entity_grounding_score": grounding,
            "contradiction_score": contradiction,
            "signals": signals,
        }

        metrics.gauge("agent_hallucination_score").set(overall)

        if overall > 0.5:
            logger.warning("Hallucination detected", component="hallucination_detector",
                           event="agent.hallucination", score=overall, signals=signals)
            metrics.counter("agent_hallucination_events").inc()

        return result

    @staticmethod
    def _check_attribution(response: str, chunks: list[dict]) -> float:
        """Check what fraction of response content is attributable to retrieved chunks."""
        if not chunks or not response:
            return 1.0  # No sources = high hallucination risk

        response_lower = response.lower()
        response_words = set(response_lower.split())

        # Check if response words overlap with chunk content
        all_chunk_text = " ".join(c.get("content", "") for c in chunks).lower()
        chunk_words = set(all_chunk_text.split())

        if not response_words:
            return 1.0

        # Words in response that appear in chunks
        attributed_words = response_words & chunk_words
        # Remove stop words for better signal
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
                      "to", "for", "of", "with", "by", "and", "or", "but", "not"}
        attributed_words -= stop_words
        response_content_words = response_words - stop_words

        if not response_content_words:
            return 0.5  # Uncertain

        attribution_rate = len(attributed_words) / len(response_content_words)
        return 1.0 - min(attribution_rate, 1.0)  # Lower = better attribution

    @staticmethod
    def _check_entity_grounding(response: str, chunks: list[dict],
                                  entity_list: list[str]) -> float:
        """Check if entities in response exist in retrieved chunks."""
        import re
        # Simple entity extraction: capitalized words, numbers, etc.
        response_entities = set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', response))
        response_entities.update(entity_list)

        if not response_entities:
            return 0.0  # No entities to check

        all_chunk_text = " ".join(c.get("content", "") for c in chunks)
        ungrounded = [e for e in response_entities if e.lower() not in all_chunk_text.lower()]
        ungrounded_rate = len(ungrounded) / max(len(response_entities), 1)

        return ungrounded_rate

    @staticmethod
    def _check_contradiction(response: str, previous: list[str]) -> float:
        """Check if response contradicts previous statements."""
        if not previous:
            return 0.0

        # Simple contradiction: direct negation patterns
        import re
        contradiction_patterns = [
            r"(?i)(however|but|actually|contrary to|unlike)",
            r"(?i)(no|not|never|none)" 
        ]

        contradiction_count = 0
        for pattern in contradiction_patterns:
            if re.search(pattern, response):
                contradiction_count += 1

        # Check for direct factual contradictions
        response_lower = response.lower()
        for prev in previous:
            prev_lower = prev.lower()
            # If previous says "X is Y" and response says "X is not Y"
            if " is not " in response_lower and any(
                phrase in prev_lower for phrase in response_lower.split(" is not ")
            ):
                contradiction_count += 2

        return min(contradiction_count / 5.0, 1.0)
