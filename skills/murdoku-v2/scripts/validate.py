"""MURDOKU puzzle.json 契约校验。

这是"保证大模型读题不出错"的落点：把能用代码判定的错误（房间不连通、
漏格、can_place 矛盾、行列冲突）在进入推理之前拦下来。

房间连通性用四邻接广度优先；房间是"粗线围出的不规则区域"，必然连通。
"""
import json
from collections import defaultdict, deque
from pathlib import Path

from board_geometry import cell_name, parse_cell_name

REQUIRED_KEYS = ("source_image", "grid", "victim", "global_clues",
                 "suspects", "cells", "rooms", "resolution_notes")

VALID_GENDERS = ("M", "F", "?")


def load_puzzle(path) -> dict:
    with open(Path(path), "r", encoding="utf-8") as f:
        return json.load(f)


def _rid(value) -> str:
    """房间号归一化成字符串，容忍 JSON 里写成 int 或 str"""
    return "" if value is None else str(value)


def validate_puzzle(puzzle: dict, library, grid: int) -> tuple[list[str], list[str]]:
    """返回 (errors, warnings)。errors 非空表示必须回修。"""
    errors: list[str] = []
    warnings: list[str] = []

    # 1) 结构
    for key in REQUIRED_KEYS:
        if key not in puzzle:
            errors.append(f"❌ [结构] 缺少必需字段: {key}")
    if errors:
        return errors, warnings
    if puzzle["grid"] != grid:
        errors.append(f"❌ [结构] grid 不一致: puzzle={puzzle['grid']} 期望={grid}")

    cells: dict = puzzle["cells"]
    expected = {cell_name(r, c) for r in range(grid) for c in range(grid)}

    # 2) 覆盖率
    got = set(cells)
    for m in sorted(expected - got):
        errors.append(f"❌ [覆盖率] 缺少坐标: {m}")
    for e in sorted(got - expected):
        errors.append(f"❌ [覆盖率] 多余坐标: {e}")

    # 3) 元素合法性 + 4) can_place 一致性
    names = set(library.names())
    for cn in sorted(got & expected):
        cell = cells[cn]
        element = cell.get("element")
        if element not in names:
            errors.append(f"❌ [元素] {cn} 的元素 {element!r} 不在元素库中")
            continue
        actual = library.is_placeable(element)
        declared = cell.get("can_place")
        if actual is None:
            warnings.append(f"⚠️ [can_place] 元素[{element}]可用性未收录，出现在 {cn}")
        elif bool(declared) != bool(actual):
            errors.append(
                f"❌ [can_place] {cn} 的 can_place={declared} 与元素库不符"
                f"（{element} → {actual}）")

    # 5) 房间连通性 + 收集房间成员
    by_room: dict[str, list[str]] = defaultdict(list)
    for cn in sorted(got & expected):
        rid = cells[cn].get("room_id")
        if rid is None:
            errors.append(f"❌ [房间] {cn} 未标 room_id")
            continue
        by_room[_rid(rid)].append(cn)

    for rid, members in by_room.items():
        member_set = set(members)
        start = members[0]
        seen = {start}
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            row, col = parse_cell_name(cur, grid)
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = row + dr, col + dc
                if 0 <= nr < grid and 0 <= nc < grid:
                    nb = cell_name(nr, nc)
                    if nb in member_set and nb not in seen:
                        seen.add(nb)
                        queue.append(nb)
        if len(seen) != len(member_set):
            orphan = sorted(member_set - seen)[0]
            errors.append(f"❌ [房间连通性] 房间 {rid} 的 {orphan} 与其余格子不连通")

    # 6) rooms 与 cells 互为逆映射
    rooms: dict = puzzle["rooms"]
    for rid, info in rooms.items():
        for cn in info.get("cells", []):
            actual = _rid(cells.get(cn, {}).get("room_id"))
            if actual != _rid(rid):
                errors.append(
                    f"❌ [房间映射] rooms[{rid}] 含 {cn}，但该格 room_id={actual or '未标'}")
    for rid, members in by_room.items():
        declared = {str(x) for x in rooms.get(rid, {}).get("cells", [])}
        if declared != set(members):
            diff = sorted(set(members) - declared) or sorted(declared - set(members))
            errors.append(f"❌ [房间映射] 房间 {rid} 的 cells 与格子标注不符，例: {diff[:3]}")

    # 7) 嫌疑人
    seen_names: set = set()
    for s in puzzle["suspects"]:
        name = s.get("name")
        if name in seen_names:
            errors.append(f"❌ [嫌疑人] 姓名重复: {name}")
        seen_names.add(name)
        if s.get("gender") not in VALID_GENDERS:
            errors.append(f"❌ [嫌疑人] {name} 的 gender 非法: {s.get('gender')!r}"
                          f"，应为 {VALID_GENDERS} 之一")

    return errors, warnings
