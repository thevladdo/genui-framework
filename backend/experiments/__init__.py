"""
Experimentation: holdout assignment for measuring personalization uplift.
"""

from .assignment import ARM_CONTROL, ARM_NONE, ARM_PERSONALIZED, assign_arm

__all__ = ["ARM_CONTROL", "ARM_NONE", "ARM_PERSONALIZED", "assign_arm"]
