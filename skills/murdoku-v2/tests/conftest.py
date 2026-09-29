"""pytest 共享配置：把 scripts/ 加入 import 路径，提供样张 fixture。"""
import sys
from pathlib import Path

import cv2
import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# 样张：与元素库标定源同一盘面（白色婚礼 9x9），已实测验证
SAMPLE_IMAGE = SKILL_ROOT / "91a19b52-9326-43d5-9f5a-7874d32672ab.jpeg"


@pytest.fixture(scope="session")
def sample_image_path() -> Path:
    """样张路径，缺失则直接失败而不是跳过——它是全部回归测试的基础。"""
    assert SAMPLE_IMAGE.exists(), f"样张缺失: {SAMPLE_IMAGE}"
    return SAMPLE_IMAGE


@pytest.fixture(scope="session")
def sample_board(sample_image_path):
    """样张归一化后的 450x450 棋盘，整个会话复用。"""
    import board_geometry as bg
    board, _rect = bg.board_from_image(
        sample_image_path, bg.DEFAULT_GRID, bg.DEFAULT_CELL_SIZE)
    return board
