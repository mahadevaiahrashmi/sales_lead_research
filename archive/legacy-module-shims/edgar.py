# agent-notes: { ctx: "shim — moved to sales_lead_research.discovery.edgar; retired in W1.3", deps: [sales_lead_research.discovery.edgar], state: deprecated, last: "sato@2026-04-22" }
"""Shim: this module moved to ``sales_lead_research.discovery.edgar``.

Kept for one wave so in-flight imports keep working. Retired in W1.3 (issue #14).
"""

import sys

from sales_lead_research.discovery import edgar as _new

sys.modules[__name__] = _new
