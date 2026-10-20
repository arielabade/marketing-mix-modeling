"""Save, load and promote model versions.

Role in the pipeline
    The train job writes a version; the evaluate job attaches metrics; promote
    moves the production pointer only if the version passed its gates; the API
    and the optimise job read whatever production points to.
Input
    A fitted MMM plus metadata (data window, config, diagnostics).
Output
    ``<registry>/<version>/``:
        model.nc         full PyMC-Marketing model (InferenceData), for refits/analysis
        posterior.parquet  thinned draws of beta, lam, alpha per channel (enough to
                         serve curves and optimise without PyMC)
        metadata.json    window, scales, diagnostics, metrics, current spend
    ``<registry>/production.json``: {"<name>": "<version>"} pointers.
Dependencies
    pandas/pyarrow, json. Storing on a mounted bucket (GCS Fuse) works unchanged.

Promotion gate
    r-hat < 1.01 and zero divergences. A model that did not converge is kept for
    inspection but never served.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..model.posterior import ChannelPosterior


class PromotionRefused(RuntimeError):
    pass


class Registry:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ write
    def save(self, name: str, mmm, posterior: ChannelPosterior, metadata: dict, draws_to_keep: int = 1000) -> str:
        version = f"{name}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
        d = self.root / version
        d.mkdir(parents=True)
        if mmm is not None:
            mmm.save(str(d / "model.nc"))
        posterior.thin(draws_to_keep).to_frame().to_parquet(d / "posterior.parquet", index=False)
        meta = {"version": version, "name": name, "created_at": datetime.now(UTC).isoformat(),
                "spend_scale": posterior.spend_scale, "target_scale": posterior.target_scale, **metadata}
        (d / "metadata.json").write_text(json.dumps(meta, indent=2, default=str))
        return version

    def update_metadata(self, version: str, **fields) -> None:
        f = self.root / version / "metadata.json"
        meta = json.loads(f.read_text())
        meta.update(fields)
        f.write_text(json.dumps(meta, indent=2, default=str))

    def promote(self, version: str, name: str | None = None, force: bool = False) -> None:
        meta = self.metadata(version)
        diag = meta.get("diagnostics", {})
        if not force and not diag.get("converged", False):
            raise PromotionRefused(f"{version} did not pass the convergence gate: {diag}")
        ptr = self._pointers()
        ptr[name or meta["name"]] = version
        (self.root / "production.json").write_text(json.dumps(ptr, indent=2))

    def delete(self, version: str) -> None:
        shutil.rmtree(self.root / version)

    # ------------------------------------------------------------------ read
    def _pointers(self) -> dict:
        f = self.root / "production.json"
        return json.loads(f.read_text()) if f.exists() else {}

    def production(self, name: str) -> str:
        ptr = self._pointers()
        if name not in ptr:
            raise FileNotFoundError(f"no production version for {name!r} in {self.root}")
        return ptr[name]

    def versions(self, name: str | None = None) -> list[str]:
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_dir() and (name is None or p.name.startswith(f"{name}-")))

    def latest(self, name: str) -> str:
        v = self.versions(name)
        if not v:
            raise FileNotFoundError(f"no version of {name!r} in {self.root}")
        return v[-1]

    def metadata(self, version: str) -> dict:
        return json.loads((self.root / version / "metadata.json").read_text())

    def posterior(self, version: str) -> ChannelPosterior:
        meta = self.metadata(version)
        df = pd.read_parquet(self.root / version / "posterior.parquet")
        return ChannelPosterior.from_frame(df, meta["spend_scale"], meta["target_scale"])

    def load_model(self, version: str):
        from pymc_marketing.mmm import MMM

        return MMM.load(str(self.root / version / "model.nc"))
