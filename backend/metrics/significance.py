"""
Statistical significance for the uplift measurement.

A raw uplift percentage is not evidence: with small samples a +100% CTR
difference can be pure noise. This module runs a two-proportion z-test
between the personalized and control arms so the stats endpoint can say
whether the difference is statistically meaningful.

Pure math (stdlib only), deliberately conservative in what it reports:
- p_value: two-tailed
- significant_95: p < 0.05
- sample_warning: flagged when either arm has < 100 impressions —
  treat any conclusion as preliminary below that.
"""

import math
from typing import Any, Dict, Optional

MIN_SOLID_SAMPLE = 100


def two_proportion_significance(
    impressions_a: int,
    clicks_a: int,
    impressions_b: int,
    clicks_b: int,
) -> Optional[Dict[str, Any]]:
    """
    Two-tailed two-proportion z-test between arm A and arm B CTRs.

    Returns None when the test cannot be computed (an arm without
    impressions, or zero variance — e.g. no clicks anywhere).
    """
    if impressions_a <= 0 or impressions_b <= 0:
        return None

    clicks_a = min(clicks_a, impressions_a)
    clicks_b = min(clicks_b, impressions_b)

    p_a = clicks_a / impressions_a
    p_b = clicks_b / impressions_b

    pooled = (clicks_a + clicks_b) / (impressions_a + impressions_b)
    variance = pooled * (1 - pooled) * (1 / impressions_a + 1 / impressions_b)
    if variance <= 0:
        return None

    z = (p_a - p_b) / math.sqrt(variance)
    # Two-tailed p-value from the standard normal distribution
    p_value = math.erfc(abs(z) / math.sqrt(2))

    return {
        "method": "two-proportion z-test (two-tailed)",
        "z_score": round(z, 3),
        "p_value": round(p_value, 5),
        "significant_95": p_value < 0.05,
        "sample_warning": (
            impressions_a < MIN_SOLID_SAMPLE or impressions_b < MIN_SOLID_SAMPLE
        ),
    }
