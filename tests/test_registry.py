"""Registry: round-trip of the posterior and the promotion gate."""

import numpy as np
import pytest

from mmm.registry.store import PromotionRefused, Registry


def test_posterior_round_trip(tmp_path, posterior):
    reg = Registry(tmp_path)
    v = reg.save("m", None, posterior, {"diagnostics": {"converged": True}})
    back = reg.posterior(v)
    assert back.channels == posterior.channels
    np.testing.assert_allclose(np.sort(back.beta[:, 0]), np.sort(posterior.beta[:, 0]))


def test_unconverged_model_is_not_promoted(tmp_path, posterior):
    reg = Registry(tmp_path)
    v = reg.save("m", None, posterior, {"diagnostics": {"converged": False, "divergences": 12}})
    with pytest.raises(PromotionRefused):
        reg.promote(v)
    with pytest.raises(FileNotFoundError):
        reg.production("m")


def test_promote_moves_the_pointer(tmp_path, posterior):
    reg = Registry(tmp_path)
    v = reg.save("m", None, posterior, {"diagnostics": {"converged": True}})
    reg.promote(v)
    assert reg.production("m") == v
