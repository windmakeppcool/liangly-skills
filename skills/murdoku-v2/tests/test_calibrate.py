"""calibrate 的目标函数测试。用合成棋盘保证结果可预期。"""
import numpy as np

import calibrate as cal


class FakeLibrary:
    def __init__(self, elements, penalty=0.5, threshold=0.6):
        self.elements = elements
        self.calibration = {"color_penalty_weight": penalty,
                            "match_threshold": threshold}


def _solid(bgr, size=38):
    return np.full((size, size, 3), bgr, np.uint8)


def _lib():
    # 每个元素 2 个模板：ground truth 格一个 + 备用实例一个。
    # 留一法下打分必须靠"同元素的另一个实例"，否则满分语义不成立。
    return FakeLibrary({
        "草地": {"templates": [{"file": "g.png", "source_cell": "R1C1"},
                               {"file": "g2.png", "source_cell": "R2C1"}],
                 "can_place": True},
        "白格": {"templates": [{"file": "w.png", "source_cell": "R1C2"},
                               {"file": "w2.png", "source_cell": "R2C2"}],
                 "can_place": True},
    })


def _cells():
    return {"R1C1": _solid((120, 200, 150)), "R2C1": _solid((120, 200, 150)),
            "R1C2": _solid((255, 255, 255)), "R2C2": _solid((255, 255, 255))}


def _full_cache():
    return {"g.png": _solid((120, 200, 150)), "g2.png": _solid((120, 200, 150)),
            "w.png": _solid((255, 255, 255)), "w2.png": _solid((255, 255, 255))}


def test_build_ground_truth_pairs_cell_with_element():
    gt = cal.build_ground_truth(_lib())
    assert sorted(gt) == [("R1C1", "草地"), ("R1C2", "白格"),
                          ("R2C1", "草地"), ("R2C2", "白格")]


def test_score_weights_perfect_on_separable_data():
    acc = cal.score_weights(_cells(), _lib(), _full_cache(), weight=0.5)
    assert acc == 1.0


def test_score_weights_returns_fraction():
    # 只有草地的两个模板在缓存里 -> 留一法下两格草地仍可互认，白格两格无从匹配
    acc = cal.score_weights(_cells(), _lib(),
                            {"g.png": _solid((120, 200, 150)),
                             "g2.png": _solid((120, 200, 150))},
                            weight=0.5)
    assert acc == 0.5      # 白格模板缺失 -> 只有草地对


def test_score_weights_excludes_own_template():
    """留一法的可证伪断言：每元素只有 1 个模板时，排除自身后无从匹配，
    必须返回 0.0。若这里不是 0.0，说明 own template 没有真的被排除。"""
    lib = FakeLibrary({
        "草地": {"templates": [{"file": "g.png", "source_cell": "R1C1"}],
                 "can_place": True},
        "白格": {"templates": [{"file": "w.png", "source_cell": "R1C2"}],
                 "can_place": True},
    })
    cells = {"R1C1": _solid((120, 200, 150)), "R1C2": _solid((255, 255, 255))}
    cache = {"g.png": _solid((120, 200, 150)), "w.png": _solid((255, 255, 255))}
    assert cal.score_weights(cells, lib, cache, weight=0.5) == 0.0


def test_score_threshold_counts_accepted_correct_and_wrong():
    cells = _cells()
    ok, bad = cal.score_threshold(cells, _lib(), _full_cache(),
                                  weight=0.5, threshold=0.6)
    assert (ok, bad) == (4, 0)      # 四格都对（靠同元素另一实例），且都过阈值


def test_score_threshold_high_threshold_rejects_everything():
    cells = _cells()
    ok, bad = cal.score_threshold(cells, _lib(), _full_cache(),
                                  weight=0.5, threshold=2.0)
    assert (ok, bad) == (0, 0)


def test_calibrate_returns_params_and_report():
    cells = _cells()
    params, report = cal.calibrate(_lib(), cells, _full_cache())
    assert set(params) == {"color_penalty_weight", "match_threshold"}
    assert params["color_penalty_weight"] in cal.WEIGHT_GRID
    assert params["match_threshold"] in cal.THRESHOLD_GRID
    assert "top-1" in report


def test_calibrate_picks_lowest_threshold_on_tie():
    """同分时（ok - bad 最大的那些阈值里）必须取最小的那个阈值。

    直接断言「选中值 == 最优增益集合的最小值」，而不是"没有更优者"式的
    反向断言——后者在同分夹具下对"取最大阈值"的实现照样通过。
    """
    cells = _cells()
    params, _ = cal.calibrate(_lib(), cells, _full_cache())
    weight = params["color_penalty_weight"]
    gains: dict[float, int] = {}
    for t in cal.THRESHOLD_GRID:
        ok, bad = cal.score_threshold(cells, _lib(), _full_cache(), weight, t)
        gains[t] = ok - bad
    best_gain = max(gains.values())
    assert params["match_threshold"] == min(
        t for t, g in gains.items() if g == best_gain)


def test_calibrate_weight_tie_picks_prior_0_5():
    """当前夹具下所有权重 top-1 同分，必须选最接近先验默认值 0.5 的权重。

    若同分规则退化为"取最小权重"会得到 0.0（把颜色惩罚整个关掉），
    这里必须失败。
    """
    cells = _cells()
    params, _ = cal.calibrate(_lib(), cells, _full_cache())
    assert params["color_penalty_weight"] == 0.5


def test_calibrate_does_not_mutate_real_library(tmp_path):
    """回归：标定不得污染调用方的元素库。

    必须用真实的 ElementLibrary 而不是 FakeLibrary —— FakeLibrary 的
    calibration 是普通属性，浅拷贝下赋值只落在副本上，掩盖问题；
    ElementLibrary 的 calibration 是只读 property 且 data 会被共享，
    只有它能暴露"标定改坏了原件"这个缺陷。
    """
    import numpy as np

    import element_library as el

    lib = el.ElementLibrary(tmp_path / "elements.json")
    lib.load()
    lib.add_template("草地", "R1C1", np.full((38, 38, 3), 120, np.uint8))
    lib.add_template("白格", "R1C2", np.full((38, 38, 3), 255, np.uint8))
    before = dict(lib.calibration)
    assert before["color_penalty_weight"] == 0.5      # 确认是默认值

    cells = {"R1C1": np.full((38, 38, 3), 120, np.uint8),
             "R1C2": np.full((38, 38, 3), 255, np.uint8)}
    cache, _ = lib.load_template_images()
    cal.calibrate(lib, cells, cache)

    assert dict(lib.calibration) == before, "标定污染了调用方的元素库"
