"""MURDOKU 棋盘几何：坐标、定位、归一化、切格、彩色 pHash。

本模块只做几何与像素运算，不读写文件（board_from_image 只读输入的截图）。
坐标口径：R{行}C{列}，行 1..N 自上而下，列 1..N 自左而右；R1C1 是左上角。
"""
import re

import cv2
import numpy as np

DEFAULT_GRID = 9
DEFAULT_CELL_SIZE = 50
DEFAULT_TILE_INSET = 6

# 棋盘定位参数（沿用 geometry.py 标定结论）
MIN_CONTOUR_AREA = 10000
BINARIZE_THRESHOLD = 30
POLY_EPS_RATIO = 0.03
ASPECT_RATIO_MIN = 0.95
ASPECT_RATIO_MAX = 1.05

_LEGACY_RE = re.compile(r"^([A-Z])(\d+)$")


# ==================== 尺寸换算 ====================

def board_px(grid: int, cell_size: int) -> int:
    """归一化后棋盘边长（像素）"""
    return grid * cell_size


def tile_px(cell_size: int, tile_inset: int) -> int:
    """单格内容块边长（内缩后）"""
    return cell_size - 2 * tile_inset


# ==================== 坐标 ====================

def cell_name(row: int, col: int) -> str:
    """0-based (行, 列) -> 'R{行+1}C{列+1}'"""
    return f"R{row + 1}C{col + 1}"


def parse_cell_name(name: str, grid: int = DEFAULT_GRID) -> tuple[int, int] | None:
    """'R3C5' -> (2, 4)。越界或格式非法返回 None。"""
    s = name.strip().upper()
    if not s.startswith("R") or "C" not in s[1:]:
        return None
    row_s, _, col_s = s[1:].partition("C")
    if not row_s.isdigit() or not col_s.isdigit():
        return None
    row, col = int(row_s) - 1, int(col_s) - 1
    if not (0 <= row < grid and 0 <= col < grid):
        return None
    return row, col


def legacy_to_rc(legacy: str, grid: int = DEFAULT_GRID) -> str | None:
    """旧口径 'A1'（行A、列1）-> 新口径 'R1C1'。无法转换返回 None。"""
    m = _LEGACY_RE.match(legacy.strip().upper())
    if m is None:
        return None
    row = ord(m.group(1)) - ord("A") + 1
    col = int(m.group(2))
    if not (1 <= row <= grid and 1 <= col <= grid):
        return None
    return f"R{row}C{col}"


# ==================== 彩色 pHash ====================

def compute_color_phash_str(tile: np.ndarray) -> str:
    """彩色感知哈希 (Color pHash)，返回 192 位的 01 字符串。

    pHash 只编码结构，纯色格子（草地/白格/粉地毯）的结构几乎相同，
    必须配合平均颜色使用，不能单独作为判据。
    """
    resized = cv2.resize(tile, (32, 32), interpolation=cv2.INTER_AREA)
    bits: list[int] = []
    for i in range(3):
        dct = cv2.dct(np.float32(resized[:, :, i]))
        roi = dct[0:8, 0:8]
        bits.extend((roi > roi.mean()).flatten().astype(int).tolist())
    return "".join(map(str, bits))


def compute_str_hamming_distance(a: str, b: str) -> int:
    """两个等长哈希字符串的汉明距离"""
    return sum(c1 != c2 for c1, c2 in zip(a, b))


# ==================== 棋盘定位与归一化 ====================

def _order_corners(pts: np.ndarray) -> np.ndarray:
    """把 4 个角点排成 [左上, 右上, 右下, 左下]，与 warp 的 dst 一一对应"""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]     # 左上：x+y 最小
    rect[1] = pts[np.argmin(diff)]  # 右上：y-x 最小
    rect[2] = pts[np.argmax(s)]     # 右下：x+y 最大
    rect[3] = pts[np.argmax(diff)]  # 左下：y-x 最大
    return rect


def locate_board(img: np.ndarray) -> np.ndarray | None:
    """二值化 + 边缘提取 -> 在暗背景中寻找最大闭合四边形轮廓。

    主路径：阈值 30 反二值化、RETR_EXTERNAL、面积 >= 10000、
    approxPolyDP(0.03*peri) 恰好 4 点、宽高比 0.95~1.05。
    兜底：主路径失败时放宽宽高比到 0.9~1.1，再退到 minAreaRect。

    返回按 [左上, 右上, 右下, 左下] 排序的 (4,2) float32，找不到返回 None。
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, BINARIZE_THRESHOLD, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 主路径：严格宽高比
    best_cnt, best_area = None, 0.0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < MIN_CONTOUR_AREA:
            continue
        approx = cv2.approxPolyDP(cnt, POLY_EPS_RATIO * cv2.arcLength(cnt, True), True)
        if len(approx) != 4:
            continue
        _, _, w, h = cv2.boundingRect(approx)
        ratio = float(w) / h
        if ASPECT_RATIO_MIN <= ratio <= ASPECT_RATIO_MAX and area > best_area:
            best_cnt, best_area = approx, area

    if best_cnt is not None:
        return _order_corners(best_cnt.reshape(4, 2))

    # 兜底 1：放宽宽高比
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < MIN_CONTOUR_AREA or area <= best_area:
            continue
        approx = cv2.approxPolyDP(cnt, POLY_EPS_RATIO * cv2.arcLength(cnt, True), True)
        if len(approx) != 4:
            continue
        _, _, w, h = cv2.boundingRect(approx)
        if 0.9 <= float(w) / h <= 1.1:
            best_cnt, best_area = approx, area

    if best_cnt is not None:
        return _order_corners(best_cnt.reshape(4, 2))

    # 兜底 2：最大轮廓的外接旋转矩形
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < MIN_CONTOUR_AREA:
        return None
    return _order_corners(cv2.boxPoints(cv2.minAreaRect(largest)).astype("float32"))


def warp_board(img: np.ndarray, rect: np.ndarray,
               grid: int = DEFAULT_GRID, cell_size: int = DEFAULT_CELL_SIZE) -> np.ndarray:
    """把原图中的棋盘透视变换到统一尺寸 grid*cell_size 见方"""
    side = board_px(grid, cell_size)
    dst = np.array([[0, 0], [side - 1, 0], [side - 1, side - 1], [0, side - 1]],
                   dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(img, M, (side, side), flags=cv2.INTER_NEAREST)


def board_from_image(image_path, grid: int = DEFAULT_GRID,
                     cell_size: int = DEFAULT_CELL_SIZE) -> tuple[np.ndarray, np.ndarray]:
    """读图 -> 定位棋盘 -> 透视变换。失败时抛出 SystemExit（附排查提示）。"""
    img = cv2.imread(str(image_path))
    if img is None:
        raise SystemExit(f"❌ 无法读取图片: {image_path}")
    rect = locate_board(img)
    if rect is None:
        raise SystemExit(
            f"❌ 未能在图像中定位到 {grid}x{grid} 棋盘: {image_path}\n"
            "   请确认截图完整包含棋盘四边（四周留出背景边距），且棋盘未被弹窗遮挡。")
    return warp_board(img, rect, grid, cell_size), rect


def extract_cells(board: np.ndarray, grid: int = DEFAULT_GRID,
                  cell_size: int = DEFAULT_CELL_SIZE,
                  tile_inset: int = DEFAULT_TILE_INSET) -> dict[str, np.ndarray]:
    """按棋盘像素分割，返回 {格坐标: 内容块}，按 R1C1..R9C9 顺序。

    内缩 tile_inset 像素以避开格子边框黑线（geometry.py 标定结论：内缩 2px 时
    边框残留使同类草地色距最高到 122，内缩 6px 后同类中位降到 31）。
    """
    cells: dict[str, np.ndarray] = {}
    for r in range(grid):
        for c in range(grid):
            y0, y1 = r * cell_size, (r + 1) * cell_size
            x0, x1 = c * cell_size, (c + 1) * cell_size
            cells[cell_name(r, c)] = board[
                y0 + tile_inset:y1 - tile_inset, x0 + tile_inset:x1 - tile_inset]
    return cells
