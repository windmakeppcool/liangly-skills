"""template_match 的打分与排序测试。"""
import numpy as np
import pytest

import template_match as tm


class FakeLibrary:
    """只带 elements / calibration 两个属性的最小替身"""
    def __init__(self, elements, penalty):
        self.elements = elements
        self.calibration = {"color_penalty_weight": penalty, "match_threshold": 0.6}


def _solid(bgr, size=38):
    return np.full((size, size, 3), bgr, np.uint8)


def _checker(size=38):
    """黑白棋盘格，结构特征明显，避免退化成纯色分支"""
    t = np.zeros((size, size, 3), np.uint8)
    t[::2, ::2] = 255
    t[1::2, 1::2] = 255
    return t


def test_per_channel_var_is_zero_for_solid_color():
    assert tm.per_channel_var(_solid((120, 200, 150))) == pytest.approx(0.0)


def test_per_channel_var_positive_for_texture():
    assert tm.per_channel_var(_checker()) > 1.0


def test_solid_cell_matches_itself_perfectly():
    tile = _solid((120, 200, 150))
    score, pixel, dist = tm.element_score(tile, tile, color_penalty_weight=0.5)
    assert dist == pytest.approx(0.0)
    assert pixel == pytest.approx(1.0)
    assert score == pytest.approx(1.0)


def test_solid_cell_scores_far_color_lower():
    tile = _solid((120, 200, 150))
    other = _solid((0, 0, 0))
    far, _, far_dist = tm.element_score(tile, other, color_penalty_weight=0.5)
    near, _, near_dist = tm.element_score(tile, tile, color_penalty_weight=0.5)
    assert far_dist > near_dist
    assert far < near


def test_textured_cell_matches_itself_better_than_other_texture():
    a = _checker()
    b = np.zeros((38, 38, 3), np.uint8)
    b[:, :19] = 255          # 左白右黑，与棋盘格结构不同
    score_a, _, _ = tm.element_score(a, a, color_penalty_weight=0.5)
    score_b, _, _ = tm.element_score(a, b, color_penalty_weight=0.5)
    assert score_a > score_b


def test_penalty_weight_zero_ignores_color():
    """同结构不同色时，权重 0 应给出与权重无关的相关性分数"""
    a = _checker()
    b = _checker()
    b = (b.astype(np.int16) // 2).astype(np.uint8)   # 同结构、整体变暗
    s0, p0, _ = tm.element_score(a, b, color_penalty_weight=0.0)
    s1, p1, _ = tm.element_score(a, b, color_penalty_weight=1.0)
    assert p0 == pytest.approx(p1)          # 像素相关性不受权重影响
    assert s0 > s1                          # 权重越大扣分越多


def test_element_score_resizes_mismatched_template():
    cell = _solid((120, 200, 150), size=38)
    tpl = _solid((120, 200, 150), size=20)
    score, _, dist = tm.element_score(cell, tpl, color_penalty_weight=0.5)
    assert dist == pytest.approx(0.0)
    assert score == pytest.approx(1.0)


def test_match_cell_ranks_correct_element_first():
    grass = _solid((120, 200, 150))
    white = _solid((255, 255, 255))
    lib = FakeLibrary({
        "草地": {"templates": [{"file": "g.png"}], "can_place": True},
        "白格": {"templates": [{"file": "w.png"}], "can_place": True},
    }, penalty=0.5)
    cache = {"g.png": grass, "w.png": white}
    results = tm.match_cell(grass, lib, cache)
    assert [r["element"] for r in results][0] == "草地"
    assert results[0]["score"] > results[1]["score"]


def test_match_cell_skips_missing_templates():
    lib = FakeLibrary({
        "草地": {"templates": [{"file": "g.png"}], "can_place": True},
        "桌子": {"templates": [{"file": "missing.png"}], "can_place": False},
    }, penalty=0.5)
    results = tm.match_cell(_solid((120, 200, 150)), lib, {"g.png": _solid((120, 200, 150))})
    assert [r["element"] for r in results] == ["草地"]


def test_match_cell_honours_skip_files():
    grass = _solid((120, 200, 150))
    lib = FakeLibrary({
        "草地": {"templates": [{"file": "a.png"}, {"file": "b.png"}], "can_place": True},
    }, penalty=0.5)
    cache = {"a.png": grass, "b.png": grass}
    results = tm.match_cell(grass, lib, cache, skip_files={"a.png"})
    assert results[0]["template"] == "b.png"


def test_best_match_respects_threshold():
    matches = [{"element": "草地", "score": 0.72}, {"element": "白格", "score": 0.10}]
    assert tm.best_match_of(matches, 0.6) == ("草地", 0.72)
    assert tm.best_match_of(matches, 0.8) == (None, 0.72)
    assert tm.best_match_of([], 0.6) == (None, 0.0)
