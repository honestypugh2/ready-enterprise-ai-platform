"""The defect taxonomy the demonstration is built around.

This is a *demonstration* taxonomy for a synthetic manufacturing line. It is
not derived from any real inspection dataset and carries no accuracy claim.
Severity here is an input to the policy engine, never a verdict: policy decides
disposition, and it is free to disagree with the taxonomy default.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.detection import DetectionSeverity

NO_DEFECT_LABEL = "no_defect"


@dataclass(frozen=True, slots=True)
class DefectClass:
    """One label the detector is trained to emit."""

    label: str
    display_name: str
    default_severity: DetectionSeverity
    safety_relevant: bool
    description: str


DEFECT_TAXONOMY: dict[str, DefectClass] = {
    NO_DEFECT_LABEL: DefectClass(
        label=NO_DEFECT_LABEL,
        display_name="No defect",
        default_severity=DetectionSeverity.NONE,
        safety_relevant=False,
        description="Surface within tolerance for the inspected station.",
    ),
    "surface_scratch": DefectClass(
        label="surface_scratch",
        display_name="Surface scratch",
        default_severity=DetectionSeverity.COSMETIC,
        safety_relevant=False,
        description="Shallow linear surface mark with no measurable depth impact.",
    ),
    "discoloration": DefectClass(
        label="discoloration",
        display_name="Discoloration",
        default_severity=DetectionSeverity.COSMETIC,
        safety_relevant=False,
        description="Colour deviation outside the reference swatch range.",
    ),
    "misalignment": DefectClass(
        label="misalignment",
        display_name="Component misalignment",
        default_severity=DetectionSeverity.MINOR,
        safety_relevant=False,
        description="Component seated outside the positional tolerance envelope.",
    ),
    "seal_gap": DefectClass(
        label="seal_gap",
        display_name="Seal gap",
        default_severity=DetectionSeverity.MAJOR,
        safety_relevant=True,
        description="Discontinuity in the sealing surface; ingress risk.",
    ),
    "weld_porosity": DefectClass(
        label="weld_porosity",
        display_name="Weld porosity",
        default_severity=DetectionSeverity.MAJOR,
        safety_relevant=True,
        description="Gas inclusion voids reducing joint strength.",
    ),
    "structural_crack": DefectClass(
        label="structural_crack",
        display_name="Structural crack",
        default_severity=DetectionSeverity.CRITICAL,
        safety_relevant=True,
        description="Propagating fracture in a load-bearing region.",
    ),
}

DEFECT_LABELS: tuple[str, ...] = tuple(DEFECT_TAXONOMY)


def severity_for(label: str) -> DetectionSeverity:
    """Taxonomy default severity. The policy engine may override it."""
    entry = DEFECT_TAXONOMY.get(label)
    return entry.default_severity if entry else DetectionSeverity.MINOR


def is_safety_relevant(label: str) -> bool:
    entry = DEFECT_TAXONOMY.get(label)
    return bool(entry and entry.safety_relevant)
