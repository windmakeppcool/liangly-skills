"""MURDOKU 元素库：v2 schema 读写、v1 迁移、模板图片加载。

设计要点：
- schema v2 给每个元素加 can_place / category / aliases。
    can_place 三态：True 可放人 / False 不可放 / None 未收录（对应 rules.md 的 ❓）
    aliases 用于把线索原文（"在一张桌子旁边"）映射回具体格子
- 模板图片缺失只记 warning 不抛异常，否则一个坏文件会让整条流水线停摆。
- 模板 PNG 的写/读走 pathlib（imencode + write_bytes / fromfile + imdecode），
    避开 cv2 窄字符路径在 Windows 上的本地码页乱码。
"""
import json
from pathlib import Path

import cv2
import numpy as np

from board_geometry import (
    DEFAULT_CELL_SIZE, DEFAULT_GRID, DEFAULT_TILE_INSET,
    compute_color_phash_str, parse_cell_name,
)

ELEMENT_SCHEMA_VERSION = 2

DEFAULT_CALIBRATION: dict = {
    "grid": DEFAULT_GRID,
    "cell_size": DEFAULT_CELL_SIZE,
    "tile_inset": DEFAULT_TILE_INSET,
    "color_penalty_weight": 0.5,
    "match_threshold": 0.6,
}

# 元素名 -> (can_place, category, aliases)
# 依据 rules.md 1.3：空地砖格 ✅、椅子 ✅、桌子 ❌、树木 ❌、花丛 ❌；沙发规则未收录。
DEFAULT_META: dict[str, tuple[bool | None, str, list[str]]] = {
    "草地":     (True,  "地面", ["草地", "草坪", "草地格"]),
    "白格":     (True,  "地面", ["白格", "白地砖", "地砖"]),
    "蓝房白":   (True,  "地面", ["蓝房白", "白色地砖"]),
    "粉地毯":   (True,  "地面", ["粉地毯", "粉色地毯", "地毯"]),
    "粉房间":   (True,  "地面", ["粉房间", "粉色过道", "过道"]),
    "椅子":     (True,  "家具", ["椅子", "一张椅子", "椅上"]),
    "沙发":     (None,  "家具", ["沙发", "一张沙发"]),
    "桌子":     (False, "家具", ["桌子", "一张桌子", "桌"]),
    "树":       (False, "装饰", ["树", "树木", "一棵树"]),
    "花丛草地": (False, "装饰", ["花", "花丛", "一丛花"]),
    "花丛灰":   (False, "装饰", ["花", "花丛", "一丛花"]),
}


def _write_png(path: Path, tile: np.ndarray) -> None:
    """用 pathlib 按正确 Unicode 名写 PNG。

    cv2.imwrite 在 Windows 上把 Python str 编成 UTF-8 字节后交给本地码页解释，
    中文文件名会落成乱码（草地 → 鑽夊湴），pathlib 的 Path.exists() 随之误报缺失，
    换到非本地码页的机器也读不到，所以写盘一律走 pathlib。
    """
    ok, buf = cv2.imencode(".png", tile)
    if not ok:
        raise IOError(f"PNG 编码失败: {path}")
    path.write_bytes(buf.tobytes())


def _read_png(path: Path) -> np.ndarray | None:
    """用 pathlib 按正确 Unicode 名读 PNG，不可读时返回 None。

    与 _write_png 对称，不经过 cv2.imread 的本地码页窄路径；
    文件不存在返回 None（不抛异常），交由调用方按缺失降级。
    """
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


class ElementLibrary:
    """元素库。元素名是唯一键，每个元素带元数据与若干模板。"""

    def __init__(self, json_path: Path):
        self.json_path = Path(json_path)
        self.data: dict = {"version": ELEMENT_SCHEMA_VERSION,
                           "calibration": dict(DEFAULT_CALIBRATION),
                           "elements": {}}

    # ---------- 属性 ----------

    @property
    def elements(self) -> dict:
        return self.data.setdefault("elements", {})

    @property
    def calibration(self) -> dict:
        return self.data.setdefault("calibration", dict(DEFAULT_CALIBRATION))

    @property
    def reference_dir(self) -> Path:
        """元素库所在目录，模板路径相对它解析"""
        return self.json_path.parent

    # ---------- 读写 ----------

    def load(self) -> None:
        """读取元素库；文件不存在时保持空结构（不报错，便于首次 add）"""
        if not self.json_path.exists():
            return
        with open(self.json_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if "elements" in loaded and "version" not in loaded:
            # v1 结构：保留原样，由调用方决定何时 migrate_from_v1()
            self.data = loaded
            return
        self.data = loaded
        self.calibration  # 触发 setdefault，补齐缺失的标定项

    def save(self) -> None:
        self.reference_dir.mkdir(parents=True, exist_ok=True)
        self.data["version"] = ELEMENT_SCHEMA_VERSION
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    # ---------- 查询 ----------

    def names(self) -> list[str]:
        return list(self.elements)

    def is_placeable(self, name: str) -> bool | None:
        """True 可放 / False 不可放 / None 未收录或元素不存在"""
        elem = self.elements.get(name)
        if elem is None:
            return None
        return elem.get("can_place")

    def aliases_of(self, name: str) -> list[str]:
        return list(self.elements.get(name, {}).get("aliases", []))

    # ---------- 模板 ----------

    def add_template(self, name: str, cell: str, tile: np.ndarray,
                     can_place: bool | None = None,
                     category: str | None = None,
                     aliases: list[str] | None = None) -> None:
        """把一块格子像素登记为该元素的一个模板（同源格覆盖更新）。"""
        if parse_cell_name(cell, grid=self.calibration["grid"]) is None:
            raise ValueError(f"非法格子坐标: {cell}")

        elem = self.elements.setdefault(name, {"templates": []})
        if can_place is not None:
            elem["can_place"] = can_place
        elif "can_place" not in elem:
            elem["can_place"] = DEFAULT_META.get(name, (None, "", []))[0]
        if category is not None:
            elem["category"] = category
        elif "category" not in elem:
            elem["category"] = DEFAULT_META.get(name, (None, "", []))[1]
        if aliases is not None:
            elem["aliases"] = list(aliases)
        elif "aliases" not in elem:
            elem["aliases"] = list(DEFAULT_META.get(name, (None, "", []))[2])

        tdir = self.reference_dir / "templates"
        tdir.mkdir(parents=True, exist_ok=True)
        fname = f"{name}__{cell}.png"
        _write_png(tdir / fname, tile)

        rel = f"templates/{fname}"
        elem["templates"] = [t for t in elem.get("templates", []) if t["file"] != rel]
        elem["templates"].append({
            "file": rel,
            "source_cell": cell,
            "phash": compute_color_phash_str(tile),
            "avg_color": [int(v) for v in tile.reshape(-1, 3).mean(axis=0)],
        })

    def load_template_images(self) -> tuple[dict[str, np.ndarray], list[str]]:
        """把元素库所有模板图片读进内存。

        返回 (缓存, warnings)。图片缺失只记 warning 并跳过该元素，
        绝不抛异常——一个坏文件不该让整条流水线停摆。
        """
        cache: dict[str, np.ndarray] = {}
        warnings: list[str] = []
        for name, elem in self.elements.items():
            missing = 0
            for t in elem.get("templates", []):
                rel = t["file"]
                if rel in cache:
                    continue
                img = _read_png(self.reference_dir / rel)
                if img is None:
                    missing += 1
                    continue
                cache[rel] = img
            if missing and not any(t["file"] in cache for t in elem.get("templates", [])):
                warnings.append(f"元素[{name}]的 {missing} 个模板图片全部缺失，已跳过")
            elif missing:
                warnings.append(f"元素[{name}]有 {missing} 个模板图片缺失，已跳过缺失部分")
        return cache, warnings

    # ---------- 迁移 ----------

    def migrate_from_v1(self, legacy_mapper=None) -> int:
        """把 v1 元素库就地升级到 v2。

        v1 -> v2 的改动：
        - source_cell 从旧口径 A1..I9 迁到 R1C1..R9C9
        - 模板文件名同步改名
        - 每个元素补 can_place / category / aliases（取自 DEFAULT_META）
        - 顶层补 version 与 calibration

        返回迁移的元素数；已是 v2 时返回 0 且不做任何改动（幂等）。
        """
        from board_geometry import legacy_to_rc

        if self.data.get("version") == ELEMENT_SCHEMA_VERSION:
            return 0

        grid = self.calibration["grid"]
        mapper = legacy_mapper or (lambda s: legacy_to_rc(s, grid))
        converted: dict = {}

        for name, elem in self.elements.items():
            can_place, category, aliases = DEFAULT_META.get(name, (None, "未分类", []))
            new_templates = []
            for t in elem.get("templates", []):
                old_cell = t.get("source_cell", "")
                new_cell = mapper(old_cell)
                if new_cell is None:
                    continue  # 坐标无法解析的旧条目直接丢弃
                new_rel = f"templates/{name}__{new_cell}.png"
                new_templates.append({
                    **t,
                    "file": new_rel,
                    "source_cell": new_cell,
                })
            converted[name] = {
                "can_place": elem.get("can_place", can_place),
                "category": elem.get("category", category),
                "aliases": elem.get("aliases", list(aliases)),
                "templates": new_templates,
            }

        self.data = {
            "version": ELEMENT_SCHEMA_VERSION,
            "calibration": dict(DEFAULT_CALIBRATION),
            "elements": converted,
        }
        return len(converted)
