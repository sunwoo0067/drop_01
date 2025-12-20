from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    job_id: str
    target_id: str
    input_data: Dict[str, Any]
    benchmark_data: Dict[str, Any]
    collected_items: List[Dict[str, Any]]
    candidate_results: List[Dict[str, Any]]
    pain_points: List[str]
    specs: Dict[str, Any]
    seasonality: Dict[str, Any]
    next_step: str
    errors: List[str]
    logs: List[str]
    final_output: Optional[Dict[str, Any]]
