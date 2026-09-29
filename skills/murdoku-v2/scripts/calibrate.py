"""MURDOKU 匹配阈值标定。

标注集是白捡的：elements.json 里每条模板都记着自己的 source_cell，
而样张与标定源是同一盘面，所以这些坐标就是现成的正确答案。

分两阶段标定（原因见实现计划 Task 5）：
  阶段 A：网格搜索 color_penalty_weight，目标 top-1 准确率最大
  阶段 B：固定权重，网格搜索 match_threshold，
          目标（接受且正确数 - 接受但错误数）最大；同分取更小阈值

打分一律走留一法（leave-one-out）：每个 ground truth 格匹配时排除
自己的模板文件，只允许同元素的其它实例作答。不排除的话自匹配恒满分，
目标函数在全部权重上饱和，同分规则会选出退化参数（权重 0.0 把颜色
惩罚整个关掉，而纯色格恰恰必须靠平均颜色区分）。同分取舍：
  权重同分 -> 取最接近先验默认值 0.5 的（关掉颜色惩罚比保留先验危险）
  阈值同分 -> 取更小的（召回优先，未识别格交大模型兜底成本更低）
"""
import copy

import template_match as tm
from element_library import DEFAULT_CALIBRATION

WEIGHT_GRID = [0.0, 0.1, 0.25, 0.4, 0.5, 0.65, 0.8, 1.0]
THRESHOLD_GRID = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60,
                  0.65, 0.70, 0.75, 0.80, 0.85, 0.90]


def build_ground_truth(library) -> list[tuple[str, str]]:
    """从元素库记录的 source_cell 构造 [(格坐标, 正确元素名), ...]"""
    pairs: list[tuple[str, str]] = []
    for name, elem in library.elements.items():
        for t in elem.get("templates", []):
            pairs.append((t["source_cell"], name))
    return pairs


def _with_weight(library, weight):
    """克隆元素库并把 color_penalty_weight 换成指定值。

    必须深拷贝 data。浅拷贝会让 clone 与原件共享同一个 data 字典，
    改权重就会污染调用方的元素库——而 ElementLibrary.calibration 是只读
    property（无 setter），也不能直接赋值替换。
    """
    clone = copy.copy(library)
    data = getattr(library, "data", None)
    if data is not None:
        clone.data = copy.deepcopy(data)
    else:
        clone.calibration = dict(library.calibration)
    clone.calibration["color_penalty_weight"] = weight
    return clone


def _own_template_file(library, cell: str, element: str) -> str | None:
    """该格在该元素名下的自身模板文件——留一法要排除的对象。"""
    for t in library.elements.get(element, {}).get("templates", []):
        if t["source_cell"] == cell:
            return t["file"]
    return None


def _loo_matches(library, tile, template_cache, cell: str, expected: str):
    """留一法匹配：排除该格自己的模板，逼打分来自同元素的其它实例。"""
    own = _own_template_file(library, cell, expected)
    skip = {own} if own is not None else None
    return tm.match_cell(tile, library, template_cache, skip_files=skip)


def score_weights(cells: dict, library, template_cache: dict,
                  weight: float) -> float:
    """指定权重下，留一法 ground truth 中正确元素排第一的比例（top-1 准确率）"""
    probe = _with_weight(library, weight)
    gt = build_ground_truth(library)
    if not gt:
        return 0.0
    correct = 0
    for cell, expected in gt:
        tile = cells.get(cell)
        if tile is None:
            continue
        matches = _loo_matches(probe, tile, template_cache, cell, expected)
        if matches and matches[0]["element"] == expected:
            correct += 1
    return correct / len(gt)


def score_threshold(cells: dict, library, template_cache: dict,
                    weight: float, threshold: float) -> tuple[int, int]:
    """指定权重与阈值下，留一法的（接受且正确数, 接受但错误数）"""
    probe = _with_weight(library, weight)
    gt = build_ground_truth(library)
    accepted_correct = 0
    accepted_wrong = 0
    for cell, expected in gt:
        tile = cells.get(cell)
        if tile is None:
            continue
        matches = _loo_matches(probe, tile, template_cache, cell, expected)
        picked, score = tm.best_match_of(matches, threshold)
        if picked is None:
            continue                      # 低于阈值，交大模型兜底
        if picked == expected:
            accepted_correct += 1
        else:
            accepted_wrong += 1
    return accepted_correct, accepted_wrong


def calibrate(library, cells: dict, template_cache: dict) -> tuple[dict, str]:
    """两阶段标定。返回 (最优参数, 文字报告)。"""
    lines: list[str] = []
    gt = build_ground_truth(library)
    lines.append(f"标定集: {len(gt)} 个已知格")

    # ---- 阶段 A：权重 ----
    weight_scores = [(w, score_weights(cells, library, template_cache, w))
                     for w in WEIGHT_GRID]
    best_acc = max(s for _w, s in weight_scores)
    # 同分取最接近先验默认值 0.5 的（留一法饱和时不至于把颜色惩罚关掉）
    prior = DEFAULT_CALIBRATION["color_penalty_weight"]
    best_weight = min((w for w, s in weight_scores if s == best_acc),
                      key=lambda w: (abs(w - prior), w))
    lines.append(f"\n阶段A 权重搜索 (目标 top-1 准确率):")
    for w, s in weight_scores:
        mark = " <- 选中" if w == best_weight else ""
        lines.append(f"  weight={w:<5} top-1={s:.1%}{mark}")

    # ---- 阶段 B：阈值 ----
    threshold_scores = [
        (t, *score_threshold(cells, library, template_cache, best_weight, t))
        for t in THRESHOLD_GRID]
    best_gain = max(ok - bad for _t, ok, bad in threshold_scores)
    # 同分取最小阈值：召回优先
    best_threshold = min(t for t, ok, bad in threshold_scores
                         if ok - bad == best_gain)
    lines.append(f"\n阶段B 阈值搜索 (固定 weight={best_weight}，"
                 f"目标 接受且正确 - 接受但错误):")
    for t, ok, bad in threshold_scores:
        mark = " <- 选中" if t == best_threshold else ""
        lines.append(f"  threshold={t:<5} 接受且正确={ok:<3} "
                     f"接受但错误={bad:<3} 增益={ok - bad}{mark}")

    params = {"color_penalty_weight": best_weight, "match_threshold": best_threshold}
    lines.append(f"\n结论: {params}")
    return params, "\n".join(lines)
