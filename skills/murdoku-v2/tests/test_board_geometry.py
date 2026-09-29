"""board_geometry 的坐标与几何测试。"""
import numpy as np
import pytest

import board_geometry as bg


# ---------- 坐标口径 ----------

def test_cell_name_is_one_based_row_col():
    assert bg.cell_name(0, 0) == "R1C1"
    assert bg.cell_name(2, 4) == "R3C5"
    assert bg.cell_name(8, 8) == "R9C9"


def test_parse_cell_name_roundtrip():
    for name in ("R1C1", "R3C5", "R9C9"):
        row, col = bg.parse_cell_name(name)
        assert bg.cell_name(row, col) == name


def test_parse_cell_name_rejects_bad_input():
    for bad in ("", "R0C1", "R1C0", "R10C1", "R1C10", "A1", "R1", "RXC1", "R1CX"):
        assert bg.parse_cell_name(bad) is None, f"应拒绝: {bad!r}"


def test_parse_cell_name_is_case_insensitive():
    assert bg.parse_cell_name("r3c5") == (2, 4)


def test_parse_cell_name_respects_grid():
    # 16 格盘上 R16C16 合法，9 格盘上不合法
    assert bg.parse_cell_name("R16C16", grid=16) == (15, 15)
    assert bg.parse_cell_name("R16C16", grid=9) is None


# ---------- 旧坐标迁移 ----------

def test_legacy_to_rc_maps_row_letter_to_row_number():
    # 旧口径 A1 = 行A(第1行) 列1
    assert bg.legacy_to_rc("A1") == "R1C1"
    assert bg.legacy_to_rc("A9") == "R1C9"
    assert bg.legacy_to_rc("H1") == "R8C1"
    assert bg.legacy_to_rc("H5") == "R8C5"
    assert bg.legacy_to_rc("I9") == "R9C9"


def test_legacy_to_rc_rejects_bad_input():
    assert bg.legacy_to_rc("J1") is None
    assert bg.legacy_to_rc("A10") is None
    assert bg.legacy_to_rc("R1C1") is None


# ---------- 尺寸换算 ----------

def test_board_and_tile_px():
    assert bg.board_px(9, 50) == 450
    assert bg.tile_px(50, 6) == 38


# ---------- 棋盘定位与切格 ----------

def test_locate_board_finds_sample_board(sample_image_path):
    import cv2
    img = cv2.imread(str(sample_image_path))
    rect = bg.locate_board(img)
    assert rect is not None, "样张应能定位到棋盘"
    assert rect.shape == (4, 2)
    # 实测样张棋盘 bbox=(436,45,593,593)
    assert abs(float(rect[:, 0].min()) - 436) < 3
    assert abs(float(rect[:, 1].min()) - 45) < 3


def test_sample_board_is_450_square(sample_board):
    assert sample_board.shape == (450, 450, 3)


def test_extract_cells_yields_81_named_tiles(sample_board):
    cells = bg.extract_cells(sample_board, 9, 50, 6)
    assert len(cells) == 81
    assert set(cells) == {bg.cell_name(r, c) for r in range(9) for c in range(9)}
    for tile in cells.values():
        assert tile.shape == (38, 38, 3)


def test_extract_cells_works_for_other_grid():
    # 9 格盘按 grid=9 cell_size=50 归一化后，用 grid=3 cell_size=150 切也是 9 块
    board = np.zeros((450, 450, 3), np.uint8)
    cells = bg.extract_cells(board, 3, 150, 6)
    assert len(cells) == 9
    assert cells[bg.cell_name(0, 0)].shape == (138, 138, 3)


# ---------- pHash ----------

def test_phash_is_192_bits_and_stable(sample_board):
    cells = bg.extract_cells(sample_board, 9, 50, 6)
    h = bg.compute_color_phash_str(cells["R1C1"])
    assert len(h) == 192
    assert set(h) <= {"0", "1"}
    # 同一输入两次结果必须一致
    assert bg.compute_color_phash_str(cells["R1C1"]) == h


def test_phash_hamming_distance_bounds(sample_board):
    cells = bg.extract_cells(sample_board, 9, 50, 6)
    a = bg.compute_color_phash_str(cells["R1C1"])
    assert bg.compute_str_hamming_distance(a, a) == 0
    b = bg.compute_color_phash_str(cells["R9C9"])
    assert 0 <= bg.compute_str_hamming_distance(a, b) <= 192
