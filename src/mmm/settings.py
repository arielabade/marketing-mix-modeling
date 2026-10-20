"""Configuration: YAML defaults + environment overrides.

Role in the pipeline
    Every job and the API read settings from here, never from hard-coded paths.
Input
    config/default.yaml, optionally config/<MMM_PROFILE>.yaml merged on top, and
    the environment variables listed in .env.example.
Output
    A plain nested dict (``load()``) plus helpers for the paths the jobs write to.
Dependencies
    PyYAML only, so importing settings never pulls in PyMC.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.environ.get("MMM_CONFIG_DIR", ROOT / "config"))

# Environment variable -> dotted key in the config. Only what legitimately
# changes between a laptop, CI and production lives here.
ENV_OVERRIDES = {
    "MMM_DATA_SOURCE": "data.source",
    "MMM_DATA_START": "data.start",
    "MMM_DATA_END": "data.end",
    "MMM_REGISTRY_PATH": "registry.path",
    "MMM_REPORTS_PATH": "reports.path",
    "MMM_DASHBOARD_PATH": "reports.dashboard",
}


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _set(cfg: dict, dotted: str, value: Any) -> None:
    *parents, leaf = dotted.split(".")
    node = cfg
    for p in parents:
        node = node.setdefault(p, {})
    node[leaf] = value


def load(profile: str | None = None) -> dict:
    """Load the configuration for a run.

    ``profile`` (or MMM_PROFILE) selects an overlay such as ``small``, used by
    CI and the end-to-end test so they exercise the same code path as a full
    run with a fraction of the sampling.
    """
    cfg = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text())
    profile = profile or os.environ.get("MMM_PROFILE")
    if profile and profile != "default":
        cfg = _merge(cfg, yaml.safe_load((CONFIG_DIR / f"{profile}.yaml").read_text()))
    for env, key in ENV_OVERRIDES.items():
        if os.environ.get(env):
            _set(cfg, key, os.environ[env])
    cfg["profile"] = profile or "default"
    return cfg


def path(cfg: dict, dotted: str) -> Path:
    """Resolve a configured path relative to the repository root."""
    node: Any = cfg
    for part in dotted.split("."):
        node = node[part]
    p = Path(node)
    return p if p.is_absolute() else ROOT / p
