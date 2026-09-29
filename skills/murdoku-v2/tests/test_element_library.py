"""element_library 的 schema、迁移与降级加载测试。"""
import json

import cv2
import numpy as np
import pytest

import element_library as el


def _v1_payload():
    """一份最小 v1 元素库（旧口径 A1..I9，无 can_place）"""
    return {
        "elements": {
            "草地": {"templates": [
                {"file": "templates/草地__A1.png", "source_cell": "A1",
                 "phash": "1" * 192, "avg_color": [128, 198, 152]},
                {"file": "templates/草地__H5.png", "source_cell": "H5",
                 "phash": "1" * 192, "avg_color": [146, 227, 174]},
            ]},
            "桌子": {"templates": [
                {"file": "templates/桌子__A5.png", "source_cell": "A5",
                 "phash": "0" * 192, "avg_color": [163, 141, 176]},
            ]},
        }
    }


@pytest.fixture
def v1_lib(tmp_path):
    p = tmp_path / "elements.json"
    p.write_text(json.dumps(_v1_payload(), ensure_ascii=False), encoding="utf-8")
    lib = el.ElementLibrary(p)
    lib.load()
    return lib


def test_migrate_converts_legacy_cells_to_rc(v1_lib):
    n = v1_lib.migrate_from_v1()
    assert n == 2
    cells = [t["source_cell"] for t in v1_lib.elements["草地"]["templates"]]
    assert cells == ["R1C1", "R8C5"]


def test_migrate_fills_meta_from_defaults(v1_lib):
    v1_lib.migrate_from_v1()
    assert v1_lib.elements["草地"]["can_place"] is True
    assert v1_lib.elements["草地"]["category"] == "地面"
    assert "草坪" in v1_lib.elements["草地"]["aliases"]
    assert v1_lib.elements["桌子"]["can_place"] is False
    assert v1_lib.elements["桌子"]["category"] == "家具"


def test_migrate_renames_template_filenames(v1_lib):
    v1_lib.migrate_from_v1()
    files = [t["file"] for t in v1_lib.elements["草地"]["templates"]]
    assert files == ["templates/草地__R1C1.png", "templates/草地__R8C5.png"]


def test_migrate_sets_schema_version_and_calibration(v1_lib):
    v1_lib.migrate_from_v1()
    assert v1_lib.data["version"] == el.ELEMENT_SCHEMA_VERSION
    assert v1_lib.calibration["grid"] == 9
    assert v1_lib.calibration["match_threshold"] == 0.6


def test_migrate_is_idempotent(v1_lib):
    v1_lib.migrate_from_v1()
    first = json.dumps(v1_lib.data, sort_keys=True, ensure_ascii=False)
    assert v1_lib.migrate_from_v1() == 0  # 已是 v2，不再迁移
    assert json.dumps(v1_lib.data, sort_keys=True, ensure_ascii=False) == first


def test_is_placeable_tristate(v1_lib):
    v1_lib.migrate_from_v1()
    assert v1_lib.is_placeable("草地") is True
    assert v1_lib.is_placeable("桌子") is False
    assert v1_lib.is_placeable("不存在的元素") is None
    # 沙发在 DEFAULT_META 里是未收录
    v1_lib.elements["沙发"] = {"templates": []}
    assert v1_lib.is_placeable("沙发") is None


def test_missing_template_image_degrades_not_raises(v1_lib, tmp_path):
    """模板图片全部缺失时只记 warning，不抛异常——这是本任务最关键的行为。"""
    v1_lib.migrate_from_v1()
    cache, warnings = v1_lib.load_template_images()
    assert cache == {}
    assert len(warnings) == 2
    assert any("草地" in w for w in warnings)


def test_load_template_images_reads_existing_files(v1_lib, tmp_path):
    v1_lib.migrate_from_v1()
    tdir = v1_lib.json_path.parent / "templates"
    tdir.mkdir(parents=True, exist_ok=True)
    for t in v1_lib.elements["草地"]["templates"]:
        # 夹具写盘与库自身的写盘口径一致（imencode + write_bytes）：
        # cv2.imwrite 在 Windows 上会把中文文件名落成乱码，读不回来
        ok, buf = cv2.imencode(".png", np.full((38, 38, 3), 200, np.uint8))
        assert ok
        (v1_lib.json_path.parent / t["file"]).write_bytes(buf.tobytes())
    cache, warnings = v1_lib.load_template_images()
    assert set(cache) == {"templates/草地__R1C1.png", "templates/草地__R8C5.png"}
    assert len(warnings) == 1  # 桌子模板缺失
    assert any("桌子" in w for w in warnings)


def test_chinese_filename_roundtrip(tmp_path):
    """中文文件名回环：pathlib 看得到、名字是正确 Unicode、库能读回像素。

    cv2.imwrite 在 Windows 上按本地码页写非 ASCII 文件名（草地 → 鑽夊湴），
    导致 Path.exists() 误报缺失、跨机器不可用；写盘必须走 pathlib。
    """
    lib = el.ElementLibrary(tmp_path / "elements.json")
    lib.load()
    lib.add_template("草地", "R1C1", np.full((38, 38, 3), 120, np.uint8))

    tdir = tmp_path / "templates"
    target = tdir / "草地__R1C1.png"
    assert target.exists(), "pathlib 看不到刚写入的模板文件"
    # 磁盘上只有正确 Unicode 名的那一个文件，没有乱码副本/幽灵文件
    assert sorted(p.name for p in tdir.iterdir()) == ["草地__R1C1.png"]

    cache, warnings = lib.load_template_images()
    assert warnings == []
    assert set(cache) == {"templates/草地__R1C1.png"}
    assert cache["templates/草地__R1C1.png"].shape == (38, 38, 3)


def test_add_template_creates_element_with_meta(tmp_path):
    p = tmp_path / "elements.json"
    lib = el.ElementLibrary(p)
    lib.load()
    lib.add_template("新元素", "R2C2", np.full((38, 38, 3), 90, np.uint8),
                     can_place=True, category="地面", aliases=["新块"])
    t = lib.elements["新元素"]["templates"][0]
    assert t["source_cell"] == "R2C2"
    assert t["file"] == "templates/新元素__R2C2.png"
    assert lib.elements["新元素"]["can_place"] is True
    assert lib.elements["新元素"]["aliases"] == ["新块"]
    assert len(t["phash"]) == 192


def test_add_template_overwrites_same_source_cell(tmp_path):
    lib = el.ElementLibrary(tmp_path / "elements.json")
    lib.load()
    tile = np.full((38, 38, 3), 90, np.uint8)
    lib.add_template("草地", "R1C1", tile)
    lib.add_template("草地", "R1C1", tile)
    assert len(lib.elements["草地"]["templates"]) == 1


def test_save_and_reload_roundtrip(tmp_path):
    p = tmp_path / "elements.json"
    lib = el.ElementLibrary(p)
    lib.load()
    lib.add_template("草地", "R1C1", np.full((38, 38, 3), 90, np.uint8))
    lib.save()
    again = el.ElementLibrary(p)
    again.load()
    assert again.elements["草地"]["templates"][0]["source_cell"] == "R1C1"
    assert again.data["version"] == el.ELEMENT_SCHEMA_VERSION
