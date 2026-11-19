import pytest
from gameplay import utility_ai as mod

CASES = [
    ("normalize", 'm.normalize(5, 0, 10) == approx(0.5)'),
    ("clamp", 'm.clamp01(1.5) == 1'),
    ("curve", 'm.score_curve(0.5, 2) == approx(0.25)'),
    ("cooldown", 'm.cooldown_ready(0) is True'),
    ("target", 'm.target_occupy(1, [2]) is True'),
    ("fresh", 'm.blackboard_fresh(10, 9, 2) is True'),
    ("interrupt", 'm.interrupt_propagate("active", "root") == "root"'),
    ("tick", 'm.tick_dedupe(5, 4) is True'),
    ("phase", 'm.phase_idempotent(2, 1) is True'),
    ("path", 'm.path_fallback("failed") == "wait"'),
    ("sep", 'm.separation_force(5, 3) == 3'),
    ("seed", 'm.ai_seed(1, 2) == (1, 2)'),
    ("lod", 'm.lod_tick(30, 10) == 10'),
    ("lod_far", 'm.lod_tick(100, 10) == 5'),
    ("perception", 'm.perception_lost(True, 3) == 3')
]

@pytest.mark.parametrize("name,expr", CASES, ids=[c[0] for c in CASES])
def test_contract(name, expr):
    assert eval(expr, {"m": mod, "approx": pytest.approx})
