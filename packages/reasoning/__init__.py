"""Foundation model plane.

This is where a language model earns its place: explanation, not authority.

What a reasoner may do — explain a prediction, summarise evidence, identify
missing information, propose (never decide) a next action.

What no reasoner can do, enforced by contract shape rather than by prompt
wording — change an authoritative value, calculate a regulated figure, approve
an action, bypass policy, write to a system of record, or select a tool it was
not granted.
"""

from reasoning.base import Reasoner, ReasoningUnavailableError, UngroundedOutputError
from reasoning.factory import build_reasoner
from reasoning.foundry import FoundryReasoner
from reasoning.mock import MockReasoner
from reasoning.prompts import (
    OUTPUT_SCHEMA,
    PROMPT_ID,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    RenderedPrompt,
    render,
)

__all__ = [
    "OUTPUT_SCHEMA",
    "PROMPT_ID",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "FoundryReasoner",
    "MockReasoner",
    "Reasoner",
    "ReasoningUnavailableError",
    "RenderedPrompt",
    "UngroundedOutputError",
    "build_reasoner",
    "render",
]
