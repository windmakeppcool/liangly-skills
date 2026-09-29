"""MURDOKU 产出图渲染：棋盘标注图、未识别格拼接图、嫌疑人面板裁切。

约束：cv2.putText 只支持 ASCII。因此图上标签一律用格坐标或元素编号，
中文元素名只出现在 JSON 与控制台输出里。
"""
import cv2
import numpy as np

from board_geometry import DEFAULT_CELL_SIZE, DEFAULT_GRID, DEFAULT_TILE_INSET, tile_px

# 元素编号配色，循环使用
PALETTE: list[tuple[int, int, int]] = [
    (0, 200, 0), (255, 120, 0), (0, 120, 255), (255, 0, 160),
    (0, 220, 220), (180, 0, 255), (0, 0, 255), (128, 128, 0),
    (0, 128, 128), (255, 255, 0), (128, 0, 255), (0, 255, 128),
]

UNMATCHED_COLOR = (0, 0, 255)   # 未识别：红框


def render_annotated(board: np.ndarray, cell_records: list[dict],
                     element_index: dict[str, int],
                     grid: int = DEFAULT_GRID,
                     cell_size: int = DEFAULT_CELL_SIZE) -> np.ndarray:
    """棋盘 + 格坐标 + 元素编号 + 未识别红框 ?。不修改输入数组。"""
    annotated = board.copy()
    for rec in cell_records:
        r, c = rec["row"], rec["col"]
        name = rec["cell"]
        y0, y1 = r * cell_size, (r + 1) * cell_size
        x0, x1 = c * cell_size, (c + 1) * cell_size

        matched = rec.get("best_match")
        if matched is not None:
            idx = element_index.get(matched, 0)
            color = PALETTE[(idx - 1) % len(PALETTE)] if idx else (200, 200, 200)
        else:
            color = UNMATCHED_COLOR

        cv2.rectangle(annotated, (x0 + 2, y0 + 2), (x1 - 2, y1 - 2), color, 2)
        cv2.putText(annotated, name, (x0 + 4, y0 + 13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1, cv2.LINE_AA)

        cx, cy = x0 + cell_size // 2 - 6, y0 + cell_size // 2 + 6
        if matched is not None:
            label = str(element_index.get(matched, 0))
            cv2.putText(annotated, label, (cx, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2, cv2.LINE_AA)
            cv2.putText(annotated, label, (cx, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        else:
            cv2.putText(annotated, "?", (cx + 1, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, UNMATCHED_COLOR, 2, cv2.LINE_AA)

        cv2.line(annotated, (x0, y0), (x1, y0), (60, 60, 60), 1)
        cv2.line(annotated, (x0, y0), (x0, y1), (60, 60, 60), 1)

    return annotated


def render_unmatched(cells: dict[str, np.ndarray], unmatched: list[str],
                     cell_size: int = DEFAULT_CELL_SIZE,
                     tile_inset: int = DEFAULT_TILE_INSET,
                     scale: int = 4, per_row: int = 6,
                     max_tiles: int = 24) -> np.ndarray | None:
    """未识别格子拼接总览图：每格放大 scale 倍，上方白色标签带写格坐标。

    未识别格多于 max_tiles 时只画前 max_tiles 个，并在底部注明总数。
    全部识别到位时返回 None。
    """
    if not unmatched:
        return None

    shown = unmatched[:max_tiles]
    big = tile_px(cell_size, tile_inset) * scale
    label_h = 22
    gap = 8
    rows = (len(shown) + per_row - 1) // per_row

    width = per_row * big + (per_row + 1) * gap
    height = rows * (label_h + big + gap) + gap
    extra = 26 if len(unmatched) > max_tiles else 0
    canvas = np.full((height + extra, width, 3), 255, np.uint8)

    for i, name in enumerate(shown):
        r, c = divmod(i, per_row)
        x = gap + c * (big + gap)
        y = gap + r * (label_h + big + gap)

        canvas[y:y + label_h, x:x + big] = (230, 230, 230)
        cv2.putText(canvas, name, (x + 4, y + label_h - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

        tile = cells[name]
        upscaled = cv2.resize(tile, (big, big), interpolation=cv2.INTER_NEAREST)
        canvas[y + label_h:y + label_h + big, x:x + big] = upscaled

    if extra:
        cv2.putText(canvas, f"showing {len(shown)} of {len(unmatched)}",
                    (gap, height + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 200), 1, cv2.LINE_AA)

    return canvas


def crop_suspects(img: np.ndarray, rect: np.ndarray,
                  scale: int = 2, min_ratio: float = 0.15) -> np.ndarray | None:
    """裁出棋盘左侧的嫌疑人面板并放大。

    线索文本字号很小，不放大读不准。当棋盘左边界离图左缘太近
    （< 图宽 15%）说明不是标准布局，返回 None 让调用方跳过。
    """
    x0 = int(round(float(np.min(rect[:, 0]))))
    if x0 < img.shape[1] * min_ratio:
        return None
    panel = img[:, :x0]
    if panel.size == 0:
        return None
    h, w = panel.shape[:2]
    return cv2.resize(panel, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
