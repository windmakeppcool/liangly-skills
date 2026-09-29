"""真实元素库迁移与重建后的行为测试。

样张与元素库标定源是同一盘面（白色婚礼 9x9），所以 elements.json 里
每条模板记录的 source_cell 就是该格正确答案——现成的 ground truth。
"""
import pytest

import board_geometry as bg
import element_library as el
import template_match as tm
from conftest import SKILL_ROOT

ELEMENTS_JSON = SKILL_ROOT / "reference" / "elements.json"


@pytest.fixture(scope="module")
def library():
    lib = el.ElementLibrary(ELEMENTS_JSON)
    lib.load()
    return lib


@pytest.fixture(scope="module")
def template_cache(library):
    cache, _warnings = library.load_template_images()
    return cache


@pytest.fixture(scope="module")
def cells(sample_board):
    return bg.extract_cells(sample_board, 9, 50, 6)


def test_library_is_v2(library):
    assert library.data["version"] == el.ELEMENT_SCHEMA_VERSION


def test_all_recorded_cells_are_rc_format(library):
    for name, elem in library.elements.items():
        for t in elem["templates"]:
            assert bg.parse_cell_name(t["source_cell"]) is not None, \
                f"{name} 的 source_cell 仍是旧口径: {t['source_cell']}"


def test_no_legacy_letter_cells_remain(library):
    """v1 的 A1..I9 必须一条不剩"""
    import re
    pat = re.compile(r"^[A-I][1-9]$")
    leftovers = [t["source_cell"] for e in library.elements.values()
                 for t in e["templates"] if pat.match(t["source_cell"])]
    assert leftovers == []


def test_every_template_file_exists(library):
    """每条 JSON 记录的模板文件都必须真实存在。"""
    missing = [t["file"] for e in library.elements.values()
               for t in e["templates"]
               if not (library.reference_dir / t["file"]).exists()]
    assert missing == [], f"模板文件缺失: {missing[:5]}"


def test_template_filenames_are_correct_unicode(library):
    """磁盘文件名必须与 JSON 记录逐字一致——正确 Unicode，而非 cv2 本地编码乱码。

    cv2.imwrite 在 Windows 上会把中文文件名落成乱码（草地 → 鑽夊湴），
    Path.exists() 对乱码名是 False，跨机器也读不到，所以必须双向比对文件名。
    """
    recorded = {t["file"].rsplit("/", 1)[1]
                for e in library.elements.values() for t in e["templates"]}
    tdir = library.reference_dir / "templates"
    on_disk = {p.name for p in tdir.glob("*.png")}
    assert on_disk == recorded, (
        f"文件名不一致: 多出 {sorted(on_disk - recorded)[:3]}"
        f" / 缺少 {sorted(recorded - on_disk)[:3]}")
    assert (tdir / "树__R1C9.png").exists()


def test_template_count_preserved(library):
    """迁移不该丢模板：v1 原有 81 条（9x9 全盘一格一模板）"""
    total = sum(len(e["templates"]) for e in library.elements.values())
    assert total == 81


def test_can_place_matches_rules(library):
    assert library.is_placeable("草地") is True
    assert library.is_placeable("椅子") is True
    assert library.is_placeable("桌子") is False
    assert library.is_placeable("树") is False
    assert library.is_placeable("花丛草地") is False
    assert library.is_placeable("花丛灰") is False
    assert library.is_placeable("沙发") is None   # 规则未收录


def test_aliases_present_for_every_element(library):
    for name, elem in library.elements.items():
        assert elem.get("aliases"), f"{name} 缺少 aliases"


# ---------- golden：模板匹配应还原出标定时的元素分布 ----------

TREE_CELLS = ["R1C9", "R2C1", "R4C9", "R7C9", "R8C1"]   # 旧 A9/B1/D9/G9/H1
CHAIR_CELLS = ["R4C4", "R5C3", "R5C4", "R5C6", "R4C6", "R5C7", "R7C4", "R7C6", "R7C7"]


def test_golden_trees_classified_as_tree(library, template_cache, cells):
    """五棵树必须判为「树」。这条测试会捕获坐标迁移错误、切格偏移、warp 错位。"""
    for cn in TREE_CELLS:
        matches = tm.match_cell(cells[cn], library, template_cache)
        assert matches, f"{cn} 无任何候选项"
        assert matches[0]["element"] == "树", \
            f"{cn} 判成了 {matches[0]['element']}（分数 {matches[0]['score']}）"


def test_golden_tree_generalizes_across_instances(library, template_cache, cells):
    """留一法：拿掉该格自己的模板后，仍应靠其它树模板判为「树」。

    这是真正的泛化测试——排除自我匹配的平凡通过。
    """
    for cn in TREE_CELLS:
        own = next(t["file"] for t in library.elements["树"]["templates"]
                   if t["source_cell"] == cn)
        matches = tm.match_cell(cells[cn], library, template_cache, skip_files={own})
        assert matches[0]["element"] == "树", \
            f"{cn} 去掉自身模板后判成了 {matches[0]['element']}"


def test_golden_chairs_classified_as_chair(library, template_cache, cells):
    for cn in CHAIR_CELLS:
        matches = tm.match_cell(cells[cn], library, template_cache)
        assert matches[0]["element"] == "椅子", \
            f"{cn} 判成了 {matches[0]['element']}"


def test_ground_truth_top1_accuracy_is_high(library, template_cache, cells):
    """全部 81 个已知格中，正确元素排第一的比例。

    这条不是通过/失败的性能断言，而是把准确率钉成一个数字防止回退。
    当前标定参数下的基线由本测试首次运行结果确定，之后不得下降。
    """
    total = 0
    correct = 0
    for name, elem in library.elements.items():
        for t in elem["templates"]:
            cn = t["source_cell"]
            matches = tm.match_cell(cells[cn], library, template_cache)
            total += 1
            if matches and matches[0]["element"] == name:
                correct += 1
    accuracy = correct / total
    print(f"\nGround truth top-1 准确率: {correct}/{total} = {accuracy:.1%}")
    assert accuracy >= 0.85, f"top-1 准确率过低: {accuracy:.1%}"
