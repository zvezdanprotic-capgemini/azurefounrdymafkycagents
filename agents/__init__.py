"""
MAF Agents - Entry point and registry

This module provides the agent factory registry and workflow steps.
Individual agents are defined in separate files.
"""
from typing import Dict, Any

# Import all agents
from agents.intake_agent import IntakeAgent
from agents.verification_agent import VerificationAgent
from agents.eligibility_agent import EligibilityAgent
from agents.recommendation_agent import RecommendationAgent
from agents.compliance_agent import ComplianceAgent
from agents.action_agent import ActionAgent


# Agent factory registry
AGENT_FACTORIES: Dict[str, Any] = {
    "intake": IntakeAgent.create,
    "verification": VerificationAgent.create,
    "eligibility": EligibilityAgent.create,
    "recommendation": RecommendationAgent.create,
    "compliance": ComplianceAgent.create,
    "action": ActionAgent.create,
}


# Workflow steps in order
WORKFLOW_STEPS = [
    "intake",
    "verification",
    "eligibility",
    "recommendation",
    "compliance",
    "action",
]


# Export for backward compatibility
__all__ = [
    "AGENT_FACTORIES",
    "WORKFLOW_STEPS",
    "IntakeAgent",
    "VerificationAgent",
    "EligibilityAgent",
    "RecommendationAgent",
    "ComplianceAgent",
    "ActionAgent",
]
