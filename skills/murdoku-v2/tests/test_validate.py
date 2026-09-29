"""validate 的契约校验测试。每个用例只构造一处缺陷。"""
import json

import pytest

import validate as vd


class FakeLibrary:
    def __init__(self):
        self._placeable = {"草地": True, "白格": True, "桌子": False, "沙发": None}

    def names(self):
        return list(self._placeable)

    def is_placeable(self, name):
        return self._placeable.get(name)


@pytest.fixture
def library():
    return FakeLibrary()


def _cells():
    """2x2 盘（grid=2）便于构造少量格子"""
    return {
        "R1C1": {"element": "草地", "can_place": True, "room_id": 1, "room_name": "甲"},
        "R1C2": {"element": "草地", "can_place": True, "room_id": 1, "room_name": "甲"},
        "R2C1": {"element": "白格", "can_place": True, "room_id": 2, "room_name": "乙"},
        "R2C2": {"element": "桌子", "can_place": False, "room_id": 2, "room_name": "乙"},
    }


def _puzzle():
    return {
        "source_image": "x.jpeg", "title": "测试", "grid": 2, "victim": "V",
        "global_clues": [], "resolution_notes": [],
        "suspects": [{"name": "A", "gender": "M", "clue": "线索"}],
        "cells": _cells(),
        "rooms": {"1": {"name": "甲", "cells": ["R1C1", "R1C2"]},
                  "2": {"name": "乙", "cells": ["R2C1", "R2C2"]}},
    }


def _puzzle3():
    """3x3 盘（grid=3）：房间1 = 左列，房间2 = 其余。

    连通性测试需要能构造出"同房间但不相邻"的格子，2x2 盘做不到，
    所以单独备一份 3x3 的底稿。
    """
    cells = {}
    for r in range(3):
        for c in range(3):
            rid = 1 if c == 0 else 2
            cells[f"R{r+1}C{c+1}"] = {
                "element": "草地", "can_place": True,
                "room_id": rid, "room_name": "甲" if rid == 1 else "乙"}
    right = [f"R{r+1}C{c+1}" for r in range(3) for c in (1, 2)]
    return {
        "source_image": "x.jpeg", "title": "测试", "grid": 3, "victim": "V",
        "global_clues": [], "resolution_notes": [],
        "suspects": [{"name": "A", "gender": "M", "clue": "线索"}],
        "cells": cells,
        "rooms": {"1": {"name": "甲", "cells": ["R1C1", "R2C1", "R3C1"]},
                  "2": {"name": "乙", "cells": right}},
    }


def test_valid_puzzle3_passes(library):
    errors, _ = vd.validate_puzzle(_puzzle3(), library, grid=3)
    assert errors == []


def test_valid_puzzle_passes(library):
    errors, warnings = vd.validate_puzzle(_puzzle(), library, grid=2)
    assert errors == []


def test_missing_required_key(library):
    p = _puzzle(); del p["resolution_notes"]
    errors, _ = vd.validate_puzzle(p, library, grid=2)
    assert any("resolution_notes" in e for e in errors)


def test_grid_mismatch(library):
    p = _puzzle(); p["grid"] = 9
    errors, _ = vd.validate_puzzle(p, library, grid=2)
    assert any("grid" in e for e in errors)


def test_missing_cell(library):
    p = _puzzle(); del p["cells"]["R2C2"]
    errors, _ = vd.validate_puzzle(p, library, grid=2)
    assert any("R2C2" in e and "缺少" in e for e in errors)


def test_extra_cell(library):
    p = _puzzle(); p["cells"]["R3C3"] = dict(p["cells"]["R1C1"])
    errors, _ = vd.validate_puzzle(p, library, grid=2)
    assert any("R3C3" in e and "多余" in e for e in errors)


def test_unknown_element(library):
    p = _puzzle(); p["cells"]["R1C1"]["element"] = "不存在"
    errors, _ = vd.validate_puzzle(p, library, grid=2)
    assert any("不存在" in e for e in errors)


def test_can_place_contradiction(library):
    p = _puzzle(); p["cells"]["R2C2"]["can_place"] = True   # 桌子应不可放
    errors, _ = vd.validate_puzzle(p, library, grid=2)
    assert any("can_place" in e and "R2C2" in e for e in errors)


def test_unknown_placeability_warns_not_errors(library):
    lib = FakeLibrary(); lib._placeable["绿格"] = None
    p = _puzzle(); p["cells"]["R1C1"].update(element="绿格", can_place=None)
    errors, warnings = vd.validate_puzzle(p, lib, grid=2)
    assert not any("绿格" in e for e in errors)
    assert any("绿格" in w for w in warnings)


def test_room_not_connected(library):
    """R1C1 与 R3C3 同标为房间 3，但在 3x3 盘上它们不相邻。

    注意：2x2 盘上任意两格都相邻，构造不出不连通的房间，所以这里必须用 3x3。
    """
    p = _puzzle3()
    for cn in ("R1C1", "R3C3"):
        p["cells"][cn].update(room_id=3, room_name="丙")
    p["rooms"]["1"]["cells"] = ["R2C1", "R3C1"]
    p["rooms"]["2"]["cells"] = [cn for cn in p["cells"]
                                if p["cells"][cn]["room_id"] == 2]
    p["rooms"]["3"] = {"name": "丙", "cells": ["R1C1", "R3C3"]}
    errors, _ = vd.validate_puzzle(p, library, grid=3)
    assert any("连通" in e for e in errors)


def test_rooms_reverse_mapping_mismatch(library):
    p = _puzzle()
    p["rooms"]["1"]["cells"] = ["R1C1"]        # 少了 R1C2
    errors, _ = vd.validate_puzzle(p, library, grid=2)
    assert any("房间映射" in e for e in errors)


def test_missing_room_id(library):
    p = _puzzle(); p["cells"]["R1C1"]["room_id"] = None
    errors, _ = vd.validate_puzzle(p, library, grid=2)
    assert any("room_id" in e for e in errors)


def test_duplicate_suspect_name(library):
    p = _puzzle()
    p["suspects"] = [{"name": "A", "gender": "M", "clue": "x"},
                     {"name": "A", "gender": "F", "clue": "y"}]
    errors, _ = vd.validate_puzzle(p, library, grid=2)
    assert any("重复" in e for e in errors)


def test_bad_gender(library):
    p = _puzzle(); p["suspects"][0]["gender"] = "男"
    errors, _ = vd.validate_puzzle(p, library, grid=2)
    assert any("gender" in e for e in errors)


def test_room_id_as_string_is_accepted(library):
    """JSON 里 room_id 可能写成字符串，两种写法都该通过"""
    p = _puzzle()
    p["cells"]["R1C1"]["room_id"] = "1"
    errors, _ = vd.validate_puzzle(p, library, grid=2)
    assert errors == []


def test_load_puzzle_reads_json(tmp_path):
    f = tmp_path / "puzzle.json"
    f.write_text(json.dumps(_puzzle(), ensure_ascii=False), encoding="utf-8")
    assert vd.load_puzzle(f)["grid"] == 2
