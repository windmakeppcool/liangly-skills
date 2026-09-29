"""render 的四张产出图测试。

cv2.putText 只支持 ASCII，因此图上文字只能是坐标/编号，不能是中文元素名。
"""
import numpy as np
import pytest

import render


@pytest.fixture
def board():
    return np.full((450, 450, 3), 200, np.uint8)


def _records():
    return [{"cell": "R1C1", "row": 0, "col": 0, "best_match": "草地",
             "best_score": 0.9, "matches": []},
            {"cell": "R1C2", "row": 0, "col": 1, "best_match": None,
             "best_score": 0.2, "matches": []}]


def test_render_annotated_keeps_board_size(board):
    out = render.render_annotated(board, _records(), {"草地": 1}, 9, 50)
    assert out.shape == (450, 450, 3)


def test_render_annotated_does_not_mutate_input(board):
    before = board.copy()
    render.render_annotated(board, _records(), {"草地": 1}, 9, 50)
    assert np.array_equal(board, before)


def test_render_annotated_draws_different_colors_for_matched_and_unmatched(board):
    out = render.render_annotated(board, _records(), {"草地": 1}, 9, 50)
    # 未识别格画红框 (0,0,255)，已识别格用调色板第一色 (0,200,0)
    top_left_region = out[0:50, 0:50]
    next_region = out[0:50, 50:100]
    assert not np.array_equal(top_left_region, next_region)


def test_render_unmatched_returns_none_when_nothing_unmatched(board):
    assert render.render_unmatched({}, [], 50, 6) is None


def test_render_unmatched_layout(board):
    cells = {f"R1C{i+1}": np.full((38, 38, 3), 100 + i, np.uint8) for i in range(3)}
    out = render.render_unmatched(cells, list(cells), 50, 6, scale=4, per_row=6)
    assert out is not None
    assert out.ndim == 3 and out.shape[2] == 3
    # 4 倍放大 + 标签带，尺寸必须远大于单格
    assert out.shape[0] > 150 and out.shape[1] > 150


def test_render_unmatched_caps_tile_count(board):
    cells = {f"R{r+1}C{c+1}": np.full((38, 38, 3), 100, np.uint8)
             for r in range(5) for c in range(6)}      # 30 格
    out = render.render_unmatched(cells, list(cells), 50, 6,
                                  scale=4, per_row=6, max_tiles=24)
    # 24 格 / 每行 6 个 = 4 行；30 格会是 5 行
    assert out is not None
    one_row = render.render_unmatched(cells, list(cells)[:6], 50, 6,
                                      scale=4, per_row=6, max_tiles=24)
    assert out.shape[0] == pytest.approx(one_row.shape[0] * 4, abs=10)


def test_crop_suspects_extracts_left_panel():
    img = np.full((662, 1194, 3), 50, np.uint8)
    img[:, :436] = 200                                  # 左侧面板更亮
    rect = np.array([[436, 45], [1029, 45], [1029, 638], [436, 638]], "float32")
    out = render.crop_suspects(img, rect, scale=2)
    assert out is not None
    assert out.shape[1] == 436 * 2
    assert out.mean() > 190                             # 取到的确实是左侧亮区


def test_crop_suspects_skips_when_panel_too_narrow():
    img = np.full((662, 1194, 3), 50, np.uint8)
    rect = np.array([[20, 45], [1029, 45], [1029, 638], [20, 638]], "float32")
    assert render.crop_suspects(img, rect, scale=2) is None
