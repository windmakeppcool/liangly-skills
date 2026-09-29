"""MURDOKU 棋盘预处理 CLI。

四阶段流水线的第一阶段：把游戏截图解析成结构化盘面数据。

子命令：
  parse     解析截图 -> board.png / annotated.png / unmatched.png /
            suspects.png / board.json
  add       从截图的指定格子提取模板，登记进元素库
  list      列出元素库
  validate  校验 puzzle.json（阶段2.5 的机器兜底）
  calibrate 用元素库记录的 source_cell 当 ground truth 标定匹配阈值
  migrate   把 v1 元素库升级到 v2 schema

坐标口径：R{行}C{列}，R1C1 是左上角，与游戏界面自身的 R1~R9 / C1~C9 同源。
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import cv2

from board_geometry import (
    board_px, cell_name, compute_color_phash_str, extract_cells,
    locate_board, parse_cell_name, tile_px, warp_board,
)
from element_library import ElementLibrary, ELEMENT_SCHEMA_VERSION
from template_match import best_match_of, match_cell
import render
import validate as validator
import calibrate as calibrator

SKILL_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = SKILL_ROOT / "reference"
ELEMENTS_JSON_DEFAULT = REFERENCE_DIR / "elements.json"


# ==================== parse ====================

def cmd_parse(args) -> int:
    grid = args.grid
    out_dir = Path(args.out) if args.out else SKILL_ROOT / "out"
    tiles_dir = out_dir / "cells"
    tiles_dir.mkdir(parents=True, exist_ok=True)

    img = cv2.imread(str(args.image))
    if img is None:
        print(f"❌ 无法读取图片: {args.image}")
        return 1

    # 元素库先加载：它可能覆盖 grid / cell_size / tile_inset 默认值
    library = ElementLibrary(args.elements or ELEMENTS_JSON_DEFAULT)
    library.load()
    grid = grid or library.calibration["grid"]
    cell_size = library.calibration["cell_size"]
    tile_inset = library.calibration["tile_inset"]
    threshold = library.calibration["match_threshold"]

    rect = locate_board(img)
    if rect is None:
        print(f"❌ 未能在图像中定位到 {grid}x{grid} 棋盘: {args.image}\n"
              "   请确认截图完整包含棋盘四边（四周留出背景边距），且棋盘未被弹窗遮挡。")
        return 1

    board = warp_board(img, rect, grid, cell_size)
    cells = extract_cells(board, grid, cell_size, tile_inset)

    cv2.imwrite(str(out_dir / "board.png"), board)
    for name, tile in cells.items():
        cv2.imwrite(str(tiles_dir / f"{name}.png"), tile)

    template_cache, warnings = library.load_template_images()
    element_index = {name: i + 1 for i, name in enumerate(library.names())}

    cell_records: list[dict] = []
    unmatched: list[str] = []
    for r in range(grid):
        for c in range(grid):
            name = cell_name(r, c)
            tile = cells[name]
            matches = match_cell(tile, library, template_cache) if library.elements else []
            picked, score = best_match_of(matches, threshold)
            if picked is None:
                unmatched.append(name)
            cell_records.append({
                "cell": name, "row": r, "col": c,
                "avg_color": [int(v) for v in tile.reshape(-1, 3).mean(axis=0)],
                "phash": compute_color_phash_str(tile),
                "matches": matches,
                "best_match": picked,
                "best_score": round(score, 4),
            })

    annotated = render.render_annotated(board, cell_records, element_index, grid, cell_size)
    cv2.imwrite(str(out_dir / "annotated.png"), annotated)

    montage = render.render_unmatched(cells, unmatched, cell_size, tile_inset)
    if montage is not None:
        cv2.imwrite(str(out_dir / "unmatched.png"), montage)

    panel = render.crop_suspects(img, rect)
    if panel is not None:
        cv2.imwrite(str(out_dir / "suspects.png"), panel)
    else:
        warnings.append("棋盘左边界过于靠近图左缘，跳过嫌疑人面板裁切")

    coverage: dict[str, int] = {}
    for rec in cell_records:
        if rec["best_match"] is not None:
            coverage[rec["best_match"]] = coverage.get(rec["best_match"], 0) + 1

    board_json = {
        "version": ELEMENT_SCHEMA_VERSION,
        "source_image": str(args.image),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "board": {"grid": grid, "cell_size": cell_size,
                  "board_size": board_px(grid, cell_size),
                  "tile_inset": tile_inset,
                  "tile_size": tile_px(cell_size, tile_inset)},
        "corners": [[round(float(x), 1), round(float(y), 1)] for x, y in rect],
        "calibration_used": {"color_penalty_weight": library.calibration["color_penalty_weight"],
                             "match_threshold": threshold},
        "element_index": element_index,
        "cells": cell_records,
        "unmatched": unmatched,
        "element_coverage": coverage,
        "warnings": warnings,
    }
    with open(out_dir / "board.json", "w", encoding="utf-8") as f:
        json.dump(board_json, f, indent=2, ensure_ascii=False)

    print(f"✅ 解析完成: {args.image}")
    print(f"   棋盘 -> {out_dir / 'board.png'} ({board_px(grid, cell_size)}x{board_px(grid, cell_size)})")
    print(f"   格子 -> {tiles_dir}（{grid * grid} 个 {tile_px(cell_size, tile_inset)}x{tile_px(cell_size, tile_inset)} 像素块）")
    print(f"   标注 -> {out_dir / 'annotated.png'}")
    if montage is not None:
        print(f"   未识别拼接图 -> {out_dir / 'unmatched.png'}（{len(unmatched)} 格）")
    if panel is not None:
        print(f"   嫌疑人面板 -> {out_dir / 'suspects.png'}")
    print(f"   数据 -> {out_dir / 'board.json'}")
    for w in warnings:
        print(f"   ⚠️  {w}")
    if element_index:
        print("   元素编号图例:")
        for name, idx in element_index.items():
            placeable = library.is_placeable(name)
            tag = {True: "可放", False: "不可放", None: "未收录"}[placeable]
            print(f"     {idx:>2}. {name} [{tag}]")
    print(f"   模板匹配: {grid * grid - len(unmatched)}/{grid * grid} 格已识别")
    if unmatched:
        print(f"   未识别（交多模态模型）: {', '.join(unmatched)}")
    return 0


# ==================== add ====================

def cmd_add(args) -> int:
    cells_arg = [s.strip().upper() for s in args.cells.split(",") if s.strip()]
    if not cells_arg:
        print("❌ --cells 不能为空")
        return 1

    library = ElementLibrary(args.elements or ELEMENTS_JSON_DEFAULT)
    library.load()
    grid = library.calibration["grid"]

    img = cv2.imread(str(args.image))
    if img is None:
        print(f"❌ 无法读取图片: {args.image}")
        return 1
    rect = locate_board(img)
    if rect is None:
        print(f"❌ 未能在图像中定位到 {grid}x{grid} 棋盘: {args.image}")
        return 1
    cells = extract_cells(warp_board(img, rect, grid, library.calibration["cell_size"]),
                          grid, library.calibration["cell_size"],
                          library.calibration["tile_inset"])

    aliases = [s.strip() for s in args.aliases.split(",") if s.strip()] \
        if args.aliases else None
    added = []
    for cn in cells_arg:
        if parse_cell_name(cn, grid) is None:
            print(f"❌ 非法格子坐标: {cn}（应为 R{{行}}C{{列}}，如 R3C5）")
            return 1
        library.add_template(args.name, cn, cells[cn],
                             can_place=args.placeable,
                             category=args.category, aliases=aliases)
        added.append(cn)

    library.save()
    print(f"✅ 元素[{args.name}]模板已更新: {', '.join(added)}")
    print(f"   元素库 -> {library.json_path}")
    print(f"   当前[{args.name}]共 {len(library.elements[args.name]['templates'])} 个模板")
    return 0


# ==================== list ====================

def cmd_list(args) -> int:
    library = ElementLibrary(args.elements or ELEMENTS_JSON_DEFAULT)
    library.load()
    if not library.elements:
        print("（元素库为空，用 add 子命令添加）")
        return 0
    print(f"元素库: {library.json_path}（schema v{library.data.get('version', 1)}）")
    total = 0
    for name, elem in library.elements.items():
        templates = elem.get("templates", [])
        total += len(templates)
        placeable = {True: "可放", False: "不可放", None: "未收录"}[elem.get("can_place")]
        src = ", ".join(t.get("source_cell", "?") for t in templates)
        print(f"  - {name} [{elem.get('category', '未分类')}/{placeable}] "
              f"{len(templates)} 模板 [{src}]")
    print(f"共 {len(library.elements)} 个元素, {total} 个模板")
    print(f"标定: {library.calibration}")
    return 0


# ==================== validate ====================

def cmd_validate(args) -> int:
    library = ElementLibrary(args.elements or ELEMENTS_JSON_DEFAULT)
    library.load()
    grid = args.grid or library.calibration["grid"]

    # 读取失败在 CLI 层呈现，不让裸 traceback 冒到用户面前
    # （load_puzzle 是纯库函数，保持不抛的原样，由调用方决定怎么报）
    puzzle_path = Path(args.puzzle)
    if not puzzle_path.exists():
        print(f"❌ 找不到 puzzle 文件: {args.puzzle}")
        return 1
    try:
        puzzle = validator.load_puzzle(puzzle_path)
    except (OSError, ValueError) as exc:
        print(f"❌ 无法读取 {args.puzzle}: {exc}")
        return 1
    errors, warnings = validator.validate_puzzle(puzzle, library, grid)

    for w in warnings:
        print(w)
    for e in errors:
        print(e)
    if errors:
        print(f"\n❌ 校验未通过: {len(errors)} 个错误, {len(warnings)} 个警告")
        print("   请回到阶段2修正 puzzle.json 后重跑。")
        return 1
    print(f"\n✅ 校验通过（{len(warnings)} 个警告）")
    return 0


# ==================== calibrate ====================

def cmd_calibrate(args) -> int:
    library = ElementLibrary(args.elements or ELEMENTS_JSON_DEFAULT)
    library.load()
    grid = args.grid or library.calibration["grid"]
    cell_size = library.calibration["cell_size"]
    tile_inset = library.calibration["tile_inset"]

    img = cv2.imread(str(args.image))
    if img is None:
        print(f"❌ 无法读取图片: {args.image}")
        return 1
    rect = locate_board(img)
    if rect is None:
        print(f"❌ 未能在图像中定位到 {grid}x{grid} 棋盘: {args.image}")
        return 1
    cells = extract_cells(warp_board(img, rect, grid, cell_size), grid, cell_size, tile_inset)

    template_cache, warnings = library.load_template_images()
    for w in warnings:
        print(f"⚠️  {w}")

    params, report = calibrator.calibrate(library, cells, template_cache)
    print(report)

    if args.write:
        library.calibration.update(params)
        library.save()
        print(f"\n✅ 已回写 {library.json_path} 的 calibration 段")
    else:
        print("\n（未加 --write，参数未回写）")
    return 0


# ==================== migrate ====================

def cmd_migrate(args) -> int:
    library = ElementLibrary(args.path or ELEMENTS_JSON_DEFAULT)
    library.load()
    if library.data.get("version") == ELEMENT_SCHEMA_VERSION:
        print(f"已是 schema v{ELEMENT_SCHEMA_VERSION}，无需迁移")
        return 0

    if args.dry_run:
        preview = ElementLibrary(library.json_path)
        preview.data = json.loads(json.dumps(library.data))
        n = preview.migrate_from_v1()
        print(f"[dry-run] 将迁移 {n} 个元素，改动不落盘")
        for name, elem in preview.elements.items():
            src = ", ".join(t["source_cell"] for t in elem["templates"])
            print(f"  - {name}: {src}")
        return 0

    n = library.migrate_from_v1()
    library.save()
    print(f"✅ 已迁移 {n} 个元素到 schema v{ELEMENT_SCHEMA_VERSION}")
    print("   ⚠️ 模板图片文件名已变，需重新提取以生成实际文件")
    return 0


# ==================== CLI ====================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="extract_board",
        description="MURDOKU 棋盘预处理与元素库维护")
    parser.add_argument("--elements", default=None,
                        help=f"元素库路径（默认 {ELEMENTS_JSON_DEFAULT}）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("parse", help="解析截图 -> 棋盘/格子/标注图/拼接图/面板/board.json")
    p.add_argument("image", help="游戏截图路径")
    p.add_argument("--out", default=None, help="输出目录（默认 <技能根>/out）")
    p.add_argument("--grid", type=int, default=None, help="棋盘边长（默认取元素库标定值）")
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("add", help="从截图提取格子加入元素库")
    p.add_argument("image", help="游戏截图路径")
    p.add_argument("--cells", required=True, help="逗号分隔的格坐标，如 R1C1,R2C2")
    p.add_argument("--name", required=True, help="元素名称")
    p.add_argument("--category", default=None, choices=["地面", "家具", "装饰"],
                   help="元素类别")
    p.add_argument("--placeable", default=None, action="store_true",
                   help="可放人（与 --no-placeable / --unknown-place 互斥）")
    p.add_argument("--no-placeable", dest="no_placeable", action="store_true",
                   help="不可放人")
    p.add_argument("--unknown-place", dest="unknown_place", action="store_true",
                   help="可用性未收录")
    p.add_argument("--aliases", default=None, help="线索里可能出现的叫法，逗号分隔")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="列出元素库")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("validate", help="校验 puzzle.json")
    p.add_argument("puzzle", help="puzzle.json 路径")
    p.add_argument("--grid", type=int, default=None, help="棋盘边长")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("calibrate", help="用元素库记录的 source_cell 标定匹配阈值")
    p.add_argument("image", help="用作标定的截图（须与元素库标定源同盘面）")
    p.add_argument("--grid", type=int, default=None)
    p.add_argument("--write", action="store_true", help="把结果回写元素库")
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser("migrate", help="把 v1 元素库升级到 v2 schema")
    p.add_argument("--path", default=None, help="元素库路径")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="只预览迁移结果，不落盘")
    p.set_defaults(func=cmd_migrate)

    return parser


def _force_utf8_stdio() -> None:
    """把标准输出/标准错误切到 UTF-8 并容错。

    Windows 控制台默认 cp936：中文能编码但字节不是 UTF-8（管道/重定向出去就是
    乱码），✅❌⚠️ 这类 emoji 干脆直接 UnicodeEncodeError。技能要求中文输出，
    所以入口处统一切到 utf-8。管道、已是 utf-8、或流不支持 reconfigure 的情形
    都必须无副作用、不抛异常——这是 CLI 入口，不该因为打印而挂掉。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, TypeError, AttributeError):
            # 流不支持该参数组合、或已读过无法重配 —— 打印不该让 CLI 挂掉
            pass


def main(argv: list[str] | None = None) -> int:
    # --placeable / --no-placeable / --unknown-place 三选一，合并成三元值
    _force_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "func", None) is cmd_add:
        flags = [args.placeable, args.no_placeable, args.unknown_place]
        if sum(1 for f in flags if f) > 1:
            print("❌ --placeable / --no-placeable / --unknown-place 只能选一个")
            return 1
        if args.no_placeable:
            args.placeable = False
        elif args.unknown_place:
            args.placeable = None
        elif not args.placeable:
            args.placeable = None
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
