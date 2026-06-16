"""
Holdout Assignment Module
Deterministic experiment-arm assignment for measuring personalization uplift.

The question an enterprise buyer asks is "does personalization beat my
static page?" — answerable only with a control group. With a holdout
configured, X% of identified users get the *non-personalized* render
(control), the rest get the personalized one. Comparing click-through
rates between arms gives the uplift.

Properties:
- Sticky: assignment is a pure hash of (salt, user_id) — the same user
  always lands in the same arm, across sessions and processes. Changing
  the salt reshuffles all assignments (= starts a new experiment).
- Anonymous users (no user_id) are excluded (ARM_NONE): without a stable
  identity the assignment cannot be sticky and would contaminate both arms.
"""

import hashlib
from typing import Optional

ARM_PERSONALIZED = "personalized"
ARM_CONTROL = "control"
ARM_NONE = "none"

# Bucket space: 0..9999 gives 0.01% assignment granularity
_BUCKETS = 10000


def bucket_for(user_id: str, salt: str) -> int:
    """Deterministic bucket in [0, 10000) for a user."""
    digest = hashlib.sha256(f"{salt}:{user_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % _BUCKETS


def assign_arm(
    user_id: Optional[str],
    holdout_percent: float,
    salt: str = "genui-exp-1",
) -> str:
    """
    Assign a user to an experiment arm.

    Args:
        user_id: Stable user identifier; None/empty excludes the user.
        holdout_percent: Share of users in the control arm (0-100).
            0 disables the experiment entirely (everyone personalized,
            arm reported as ARM_NONE since there is nothing to compare).
        salt: Experiment identifier; change it to start a new experiment.

    Returns:
        ARM_PERSONALIZED, ARM_CONTROL, or ARM_NONE (not in experiment).
    """
    if not user_id or holdout_percent <= 0:
        return ARM_NONE

    threshold = min(holdout_percent, 100.0) * _BUCKETS / 100.0
    if bucket_for(user_id, salt) < threshold:
        return ARM_CONTROL
    return ARM_PERSONALIZED
