"""The model must never see the answer key.

Two layers: a static scan (no modelling module may even mention the ground
truth location) and a runtime guard (every data source refuses those reads).
"""

import ast
from pathlib import Path

import pandas as pd
import pytest

from mmm.data import guard
from mmm.data.source import ParquetSource

SRC = Path(__file__).resolve().parents[1] / "src" / "mmm"
ALLOWED = {SRC / "validation" / "ground_truth.py", SRC / "validation" / "__init__.py", SRC / "data" / "guard.py"}
FORBIDDEN = ("ground_truth", "verdade", "gabarito", "MMM_GROUND_TRUTH_DIR")


def _strings_and_names(path: Path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            yield mod
            yield from (a.name for a in node.names)


MODELLING = [p for p in SRC.rglob("*.py") if p not in ALLOWED and "validation" not in p.parts
             and p.parent.name != "jobs"]


@pytest.mark.parametrize("path", MODELLING, ids=lambda p: str(p.relative_to(SRC)))
def test_modelling_code_never_references_ground_truth(path):
    hits = [s for s in _strings_and_names(path) if any(f.lower() in s.lower() for f in FORBIDDEN)]
    assert not hits, f"{path.name} references the ground truth: {hits}"


def test_only_the_evaluate_and_report_jobs_import_validation():
    for p in (SRC / "jobs").glob("*.py"):
        names = list(_strings_and_names(p))
        if any("validation" in n for n in names):
            assert p.stem in {"evaluate", "report"}, f"{p.name} imports mmm.validation"


@pytest.mark.parametrize("ident", ["ground_truth", "data/ground_truth/contribuicao_diaria.csv",
                                   "GROUND-TRUTH.parquet", "data/verdade/x.csv", "schema_gabarito"])
def test_guard_refuses_ground_truth_identifiers(ident):
    with pytest.raises(guard.GroundTruthAccessError):
        guard.check(ident)


@pytest.mark.parametrize("ident", ["fct_mmm_vendas_regiao_diario", "tecidos_marts", "/tmp/mart_small"])
def test_guard_allows_mart_tables(ident):
    guard.check(ident)


def test_parquet_source_refuses_a_ground_truth_directory(tmp_path):
    d = tmp_path / "ground_truth"
    d.mkdir()
    pd.DataFrame({"data": ["2024-01-01"], "x": [1]}).to_parquet(d / "contribuicao_diaria.parquet")
    with pytest.raises(guard.GroundTruthAccessError):
        ParquetSource(d).read_table("contribuicao_diaria")


def test_sql_source_refuses_a_ground_truth_table():
    from mmm.data.source import SqlSource

    src = SqlSource("sqlite://")
    with pytest.raises(guard.GroundTruthAccessError):
        src.read_table("ground_truth_roi")
