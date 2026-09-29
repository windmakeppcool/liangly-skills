"""MURDOKU 像素级模板匹配。

最终匹配度 = 像素相关性 - COLOR_PENALTY_WEIGHT * 归一化颜色距离

为什么需要颜色惩罚：彩色 pHash 与 TM_CCOEFF_NORMED 都只编码结构，
纯色格子（草地/白格/粉地毯）的结构几乎相同，只看相关性会把它们互相混淆。
颜色惩罚把颜色差异折算成扣分项，权重由 calibrate 子命令标定。
"""
import cv2
import numpy as np

# 颜色欧氏距离的理论上限 sqrt(3 * 255^2)，用于把色距归一化到 0~1
MAX_COLOR_DIST = float(np.sqrt(3 * 255 * 255))


def per_channel_var(img: np.ndarray) -> float:
    """逐通道方差之和。

    不能用整体 std：纯色块（白格全 255、草地每通道各自恒定）的整体 std
    被通道间均值差抬高，但逐通道方差为 0；此时 TM_CCOEFF_NORMED 分母为 0
    会返回 1.0（错误满分），必须先检测出来走纯颜色比较分支。
    """
    return float(img.astype(np.float32).var(axis=(0, 1)).sum())


def element_score(cell_tile: np.ndarray, template_img: np.ndarray,
                  color_penalty_weight: float) -> tuple[float, float, float]:
    """单个模板的匹配度。

    返回 (最终匹配度, 像素相关性, 颜色距离)。
    模板与格子尺寸不一致时先缩放到格子尺寸。
    任一方逐通道方差趋 0（纯色块）时相关性无定义，退化为纯颜色接近度。
    """
    if template_img.shape[:2] != cell_tile.shape[:2]:
        template_img = cv2.resize(
            template_img, (cell_tile.shape[1], cell_tile.shape[0]),
            interpolation=cv2.INTER_AREA)

    color_dist = float(np.linalg.norm(
        cell_tile.reshape(-1, 3).mean(axis=0)
        - template_img.reshape(-1, 3).mean(axis=0)))

    if per_channel_var(cell_tile) < 1.0 or per_channel_var(template_img) < 1.0:
        pixel_match = max(0.0, 1.0 - color_dist / MAX_COLOR_DIST)
    else:
        pixel_match = float(cv2.matchTemplate(
            cell_tile, template_img, cv2.TM_CCOEFF_NORMED).max())
        pixel_match = max(0.0, min(1.0, pixel_match))

    final_score = pixel_match - color_penalty_weight * color_dist / MAX_COLOR_DIST
    return final_score, pixel_match, color_dist


def match_cell(cell_tile: np.ndarray, library, template_cache: dict,
               skip_files: set[str] | None = None) -> list[dict]:
    """一个格子对全元素库打分，返回按匹配度降序的候选列表。

    每个元素取自己所有模板中的最高分。模板图片缺失的元素自动跳过。
    """
    skip = skip_files or set()
    penalty = library.calibration["color_penalty_weight"]
    results: list[dict] = []

    for name, elem in library.elements.items():
        best = None
        for t in elem.get("templates", []):
            rel = t["file"]
            if rel in skip:
                continue
            tpl = template_cache.get(rel)
            if tpl is None:
                continue
            score, pixel_match, color_dist = element_score(cell_tile, tpl, penalty)
            if best is None or score > best["score"]:
                best = {
                    "element": name,
                    "score": round(score, 4),
                    "pixel_match": round(pixel_match, 4),
                    "color_dist": round(color_dist, 2),
                    "template": rel,
                }
        if best is not None:
            results.append(best)

    results.sort(key=lambda x: -x["score"])
    return results


def best_match_of(matches: list[dict], threshold: float) -> tuple[str | None, float]:
    """候选列表里分数最高的元素；低于阈值则返回 (None, 最高分)。

    最高分始终返回，便于把"差一点"的情况写进 resolution_notes 供大模型参考。
    """
    if not matches:
        return None, 0.0
    top = matches[0]
    if top["score"] >= threshold:
        return top["element"], top["score"]
    return None, top["score"]
