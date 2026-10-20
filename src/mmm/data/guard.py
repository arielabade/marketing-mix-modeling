"""Ground-truth firewall.

Role in the pipeline
    The ecommerce generator writes the true channel effects to
    ``data/ground_truth/`` (and could, in another setup, expose a
    ``ground_truth`` schema). Modelling code must never see them: a model that
    can read the answer key proves nothing. Only ``mmm.validation`` may read
    them, after a model is fitted.
Input
    Any table name, schema name or filesystem path a data source is asked to read.
Output
    Nothing, or ``GroundTruthAccessError``.
Dependencies
    None.
"""

from __future__ import annotations

import re

# Identifiers that mark the answer key, in either language of the source repo.
_FORBIDDEN = re.compile(r"ground[_\-]?truth|(^|[/_.\-])verdade($|[/_.\-])|gabarito", re.IGNORECASE)


class GroundTruthAccessError(PermissionError):
    """Raised when modelling code tries to read the generator's answer key."""


def check(identifier: str) -> None:
    """Refuse any identifier that points at ground truth.

    Called by every data source before it touches a table or a file, so the
    rule holds no matter which backend is configured.
    """
    if _FORBIDDEN.search(str(identifier)):
        raise GroundTruthAccessError(
            f"Refusing to read {identifier!r}: ground truth is only for mmm.validation, never for modelling."
        )
