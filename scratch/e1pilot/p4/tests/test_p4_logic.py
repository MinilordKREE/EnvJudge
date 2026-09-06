import sys, pathlib, random
HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1])); sys.path.insert(0, str(HERE.parents[2])); sys.path.insert(0, str(HERE.parents[3] / "eobs"))
from p4.nsat import next_m, cls_with_side


def test_m_search_rule():
    assert next_m([], 20) == 20
    assert next_m([(20, "NOEFFECT")], 20) == 18
    assert next_m([(20, "ZERO")], 20) == 21
    assert next_m([(20, "NOEFFECT"), (18, "ZERO")], 20) == 19
    assert next_m([(20, "IN-BAND")], 20) is None
    assert next_m([(20, "NOEFFECT"), (18, "NOEFFECT"), (16, "NOEFFECT"), (14, "NOEFFECT")], 20) is None
    assert next_m([(2, "NOEFFECT")], 2) is None          # never below 1


def test_classification_sides():
    assert cls_with_side(4, 4) == "NOEFFECT" and cls_with_side(0, 4) == "ZERO" and cls_with_side(2, 4) == "CONTINUE"
    assert cls_with_side(4, 8) == "IN-BAND" and cls_with_side(2, 8) == "NEAR_LOW" and cls_with_side(6, 8) == "NEAR_HIGH" and cls_with_side(7, 8) == "NOEFFECT" and cls_with_side(1, 8) == "OVERSHOOT"


def test_learnability_walk():
    """latest first; 4/4 → next earlier; 0/4 → next later; 1-3 → select; ≤ 4 candidates."""
    def walk(order, probe):
        idx, tried, sel = 0, [], None
        while idx is not None and 0 <= idx < len(order) and len(tried) < 4:
            c = order[idx]
            if c in tried: break
            tried.append(c); s = probe[c]
            if 1 <= s <= 3: sel = c; break
            idx = idx + 1 if s == 4 else idx - 1
        return sel, tried
    order = [30, 20, 10]          # latest first
    assert walk(order, {30: 4, 20: 2, 10: 0}) == (20, [30, 20])
    assert walk(order, {30: 0, 20: 2, 10: 0}) == (None, [30])            # 0/4 at the latest → later doesn't exist → stop
    assert walk(order, {30: 4, 20: 4, 10: 4}) == (None, [30, 20, 10])     # frontier at the end
    assert walk(order, {30: 4, 20: 0, 10: 1}) == (None, [30, 20])         # 4/4 then 0/4 → back to 30 (already tried) → stop


def test_omega_on_fake_env():
    """ω = share of stored successes whose verbatim replay still passes; here a fake verifier that fails runs longer than m."""
    wits = [["a"] * 5, ["a"] * 9, ["a"] * 12, ["a"] * 20]
    def omega_fake(m): return sum(len(w) <= m for w in wits) / len(wits)
    assert omega_fake(50) == 1.0 and omega_fake(10) == 0.5 and omega_fake(4) == 0.0


def test_bank_subsampling_matched():
    rnd = random.Random(20260912)
    a = list(range(23)); b = list(range(9))
    k = min(len(a), len(b))
    sa, sb = rnd.sample(a, k), rnd.sample(b, k)
    assert len(sa) == len(sb) == 9 and set(sb) == set(b)
