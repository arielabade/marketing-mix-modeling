"""Geo-lift-calibrated Bayesian marketing mix model.

Pipeline: ecommerce mart (dbt) -> mmm.data -> mmm.geolift -> mmm.model ->
mmm.optimize -> mmm.serve / mmm.report. See docs/ARCHITECTURE.md.
"""

__version__ = "0.2.0"
