"""Analytics module for replay pipeline health insights.

Usage::

    from replay.analytics.health import health_report

    # Generate health report
    report = health_report("./captures")
    print(report)
"""

from .health import health_report, HopHealth
from .trends import trend_report, WeeklyTrend
from .breakdown import breakdown_report, TypeBreakdown, SourceBreakdown, DeviceBreakdown

__all__ = [
    "health_report",
    "HopHealth",
    "trend_report",
    "WeeklyTrend",
    "breakdown_report",
    "TypeBreakdown",
    "SourceBreakdown",
    "DeviceBreakdown",
]
