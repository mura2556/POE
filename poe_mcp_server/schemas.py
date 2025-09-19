"""Data models used by the POE MCP server.

The project relies on structured responses from LLMs, therefore the schemas
attempt to be descriptive and forgiving with optional metadata while still
encouraging strongly typed consumption on the client side.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Enumerates how aggressive a crafting approach is."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BudgetTier(str, Enum):
    """Enumerates the relative resource investment for a strategy."""

    BUDGET = "budget"
    STANDARD = "standard"
    LUXURY = "luxury"


class CraftingStep(BaseModel):
    """Represents a single actionable step within a crafting strategy."""

    title: Optional[str] = Field(
        default=None,
        description="Concise name of the step (e.g., 'Alt spam for prefixes').",
    )
    description: str = Field(
        description="Detailed guidance for the user to execute the step.",
    )
    risk_level: Optional[RiskLevel] = Field(
        default=None,
        description="Risk profile for the step, when it differs from the plan.",
    )
    risk_notes: Optional[str] = Field(
        default=None,
        description="Clarify why the step falls under the selected risk tier.",
    )
    budget_tier: Optional[BudgetTier] = Field(
        default=None,
        description="Budget tier for the step, when it differs from the plan tier.",
    )
    budget_notes: Optional[str] = Field(
        default=None,
        description="Explain the cost assumptions that make the tier appropriate.",
    )
    success_criteria: Optional[str] = Field(
        default=None,
        description="Signals that tell the player when to stop the step.",
    )
    alternatives: List["CraftingStep"] = Field(
        default_factory=list,
        description="Optional alternative sub-steps that can replace this step.",
    )


class CraftingRoute(BaseModel):
    """A cohesive set of steps following a specific risk and cost profile."""

    name: Optional[str] = Field(default=None, description="Label for the route.")
    summary: Optional[str] = Field(
        default=None,
        description="High level summary describing what differentiates the route.",
    )
    risk_level: Optional[RiskLevel] = Field(
        default=None,
        description="Overall risk tier for this alternative route.",
    )
    budget_tier: Optional[BudgetTier] = Field(
        default=None,
        description="Overall budget tier for this alternative route.",
    )
    steps: List[CraftingStep] = Field(
        default_factory=list,
        description="Ordered list of steps that make up this route.",
    )


class CraftingPlan(BaseModel):
    """Top-level structure returned to clients for display."""

    title: Optional[str] = Field(
        default=None,
        description="Short headline describing the goal of the crafting plan.",
    )
    goal: Optional[str] = Field(
        default=None, description="Specific item outcome or target being pursued.")
    overview: Optional[str] = Field(
        default=None,
        description="Narrative summary of the plan before the detailed steps.",
    )
    risk_level: Optional[RiskLevel] = Field(
        default=None,
        description="Default risk tier if individual steps omit their own tier.",
    )
    risk_criteria: Optional[str] = Field(
        default=None,
        description="Describe why the plan falls into the specified risk tier.",
    )
    budget_tier: Optional[BudgetTier] = Field(
        default=None,
        description="Default budget tier if individual steps omit their own tier.",
    )
    budget_criteria: Optional[str] = Field(
        default=None,
        description="Explain the resources assumed for the plan's budget tier.",
    )
    steps: List[CraftingStep] = Field(
        default_factory=list,
        description="Primary sequence of steps recommended for the player.",
    )
    alternative_routes: List[CraftingRoute] = Field(
        default_factory=list,
        description="Additional tiered strategies that the user can choose from.",
    )


try:  # pragma: no cover - compatibility shim for pydantic v1/v2.
    CraftingStep.model_rebuild()
    CraftingRoute.model_rebuild()
    CraftingPlan.model_rebuild()
except AttributeError:  # pragma: no cover
    CraftingStep.update_forward_refs()
    CraftingRoute.update_forward_refs()
    CraftingPlan.update_forward_refs()

__all__ = [
    "RiskLevel",
    "BudgetTier",
    "CraftingStep",
    "CraftingRoute",
    "CraftingPlan",
]
