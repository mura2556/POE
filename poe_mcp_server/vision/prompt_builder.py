"""Prompt templates to steer the vision model towards structured output."""
from __future__ import annotations

from typing import Optional

from ..schemas import BudgetTier, RiskLevel


def build_crafting_prompt(goal: str, context: Optional[str] = None) -> str:
    """Return a prompt instructing the model to produce stratified plans."""

    context_block = f"Context: {context.strip()}\n" if context else ""

    tier_guidance = "\n".join(
        [
            "When outlining strategies, enumerate distinct routes for the following tiers:",
            "- Risk tiers: {risk}. Clarify the trade-offs that justify each tier.",
            "- Budget tiers: {budget}. State the resource assumptions (currency, fossils, etc.).",
            "If a tier is not viable for the goal, state it explicitly with a brief reason.",
            "For each route provide the success criteria that indicate when to stop.",
            "Nest alternative steps under `alternatives` when a different action can replace a step.",
        ]
    ).format(
        risk=", ".join(level.value for level in RiskLevel),
        budget=", ".join(tier.value for tier in BudgetTier),
    )

    json_contract = "\n".join(
        [
            "Respond with JSON matching this structure:",
            "{",
            "  \"title\": string,",
            "  \"goal\": string,",
            "  \"overview\": string,",
            "  \"risk_level\": one of [{risk_levels}],",
            "  \"risk_criteria\": string explaining why the plan fits the tier,",
            "  \"budget_tier\": one of [{budget_tiers}],",
            "  \"budget_criteria\": string explaining the cost assumptions,",
            "  \"steps\": [",
            "    {{",
            "      \"title\": string,",
            "      \"description\": string,",
            "      \"risk_level\": optional risk tier,",
            "      \"risk_notes\": optional string,",
            "      \"budget_tier\": optional budget tier,",
            "      \"budget_notes\": optional string,",
            "      \"success_criteria\": optional string,",
            "      \"alternatives\": [CraftingStep, ...]",
            "    }}",
            "  ],",
            "  \"alternative_routes\": [",
            "    {{",
            "      \"name\": string,",
            "      \"summary\": string,",
            "      \"risk_level\": risk tier,",
            "      \"budget_tier\": budget tier,",
            "      \"steps\": [CraftingStep, ...]",
            "    }}",
            "  ]",
            "}",
        ]
    ).format(
        risk_levels=", ".join(level.value for level in RiskLevel),
        budget_tiers=", ".join(tier.value for tier in BudgetTier),
    )

    return "\n".join(
        [
            "You are an expert Path of Exile crafting strategist.",
            context_block,
            f"Goal: {goal.strip()}",
            tier_guidance,
            json_contract,
            "Ensure each tiered route has explicit risk and budget rationales.",
        ]
    )


__all__ = ["build_crafting_prompt"]
