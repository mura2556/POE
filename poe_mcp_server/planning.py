"""Utilities for building strongly typed crafting plans from model output."""
from __future__ import annotations

from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from .schemas import (
    BudgetTier,
    CraftingPlan,
    CraftingRoute,
    CraftingStep,
    RiskLevel,
)


def _normalize_enum(value: Any, enum_cls):
    """Attempt to coerce a loosely formatted value into an enum member."""

    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, Mapping):
        for key in ("value", "tier", "level", "name", "id"):
            if key in value:
                return _normalize_enum(value[key], enum_cls)
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    normalized = text.replace("-", " ").replace("_", " ")
    normalized = " ".join(part for part in normalized.split())
    normalized = normalized.replace(" ", "_")
    for member in enum_cls:
        aliases = {
            member.value,
            member.name.lower(),
            member.value.replace("_", " "),
            member.name.lower().replace("_", " "),
        }
        if normalized in {alias.replace(" ", "_") for alias in aliases}:
            return member
    return None


def _coerce_step(step_data: Mapping[str, Any]) -> CraftingStep:
    description = str(step_data.get("description") or step_data.get("text") or "").strip()
    if not description:
        description = "Refer to the route summary for guidance."
    alternatives_data = step_data.get("alternatives") or step_data.get("alternative_steps")
    alternatives: Sequence[Mapping[str, Any]] = []
    if isinstance(alternatives_data, Mapping):
        alternatives = [alternatives_data]
    elif isinstance(alternatives_data, Sequence):
        alternatives = [
            alt for alt in alternatives_data if isinstance(alt, Mapping)
        ]

    return CraftingStep(
        title=step_data.get("title") or step_data.get("name"),
        description=description,
        risk_level=_normalize_enum(step_data.get("risk_level"), RiskLevel),
        risk_notes=step_data.get("risk_notes") or step_data.get("risk_explanation"),
        budget_tier=_normalize_enum(step_data.get("budget_tier"), BudgetTier),
        budget_notes=step_data.get("budget_notes") or step_data.get("budget_explanation"),
        success_criteria=step_data.get("success_criteria")
        or step_data.get("success")
        or step_data.get("stop_condition"),
        alternatives=[_coerce_step(alt) for alt in alternatives],
    )


def _coerce_route(route_data: Mapping[str, Any]) -> CraftingRoute:
    steps_data = route_data.get("steps") or route_data.get("plan") or []
    steps: Sequence[Mapping[str, Any]]
    if isinstance(steps_data, Mapping):
        steps = [steps_data]
    elif isinstance(steps_data, Sequence):
        steps = [item for item in steps_data if isinstance(item, Mapping)]
    else:
        steps = []

    return CraftingRoute(
        name=route_data.get("name") or route_data.get("title"),
        summary=route_data.get("summary") or route_data.get("description"),
        risk_level=_normalize_enum(route_data.get("risk_level"), RiskLevel),
        budget_tier=_normalize_enum(route_data.get("budget_tier"), BudgetTier),
        steps=[_coerce_step(step) for step in steps],
    )


def _extract_mapping(candidate: Any) -> MutableMapping[str, Any]:
    if isinstance(candidate, MutableMapping):
        return candidate
    if isinstance(candidate, Mapping):  # types.MappingProxyType
        return dict(candidate)
    return {}


def assemble_crafting_plan(raw_plan: Mapping[str, Any]) -> CraftingPlan:
    """Normalize arbitrary model output into a :class:`CraftingPlan` instance."""

    plan_blob = raw_plan.get("plan") if isinstance(raw_plan, Mapping) else None
    if isinstance(plan_blob, Mapping):
        plan_data = _extract_mapping(plan_blob)
    else:
        plan_data = _extract_mapping(raw_plan)

    plan_steps = plan_data.get("steps") or plan_data.get("primary_steps") or []
    if isinstance(plan_steps, Mapping):
        plan_steps = [plan_steps]
    elif isinstance(plan_steps, Sequence):
        plan_steps = [step for step in plan_steps if isinstance(step, Mapping)]
    else:
        plan_steps = []

    route_candidates: Iterable[Any] = plan_data.get("alternative_routes") or plan_data.get("routes") or []
    if isinstance(route_candidates, Mapping):
        route_candidates = [route_candidates]

    routes: list[CraftingRoute] = []
    for route in route_candidates:
        if isinstance(route, Mapping):
            routes.append(_coerce_route(route))

    return CraftingPlan(
        title=plan_data.get("title") or plan_data.get("name"),
        goal=plan_data.get("goal") or plan_data.get("item_goal"),
        overview=plan_data.get("overview") or plan_data.get("summary"),
        risk_level=_normalize_enum(plan_data.get("risk_level"), RiskLevel),
        risk_criteria=plan_data.get("risk_criteria") or plan_data.get("risk_notes"),
        budget_tier=_normalize_enum(plan_data.get("budget_tier"), BudgetTier),
        budget_criteria=plan_data.get("budget_criteria") or plan_data.get("budget_notes"),
        steps=[_coerce_step(step) for step in plan_steps],
        alternative_routes=routes,
    )


__all__ = ["assemble_crafting_plan"]
