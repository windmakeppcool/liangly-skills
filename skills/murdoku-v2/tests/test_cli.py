"""CLI 端到端测试：跑真命令，验真产物。"""
import json

import cv2

import extract_board as cli


def test_parse_produces_all_artifacts(tmp_path, sample_image_path):
    rc = cli.main(["parse", str(sample_image_path), "--out", str(tmp_path)])
    assert rc == 0

    board = cv2.imread(str(tmp_path / "board.png"))
    assert board.shape == (450, 450, 3)
    for name in ("annotated.png", "board.json"):
        assert (tmp_path / name).exists(), f"缺少产出: {name}"

    data = json.loads((tmp_path / "board.json").read_text(encoding="utf-8"))
    assert data["board"]["grid"] == 9
    assert len(data["cells"]) == 81
    assert data["cells"][0]["cell"] == "R1C1"
    assert isinstance(data["unmatched"], list)
    assert isinstance(data["warnings"], list)


def test_parse_writes_unmatched_montage_when_needed(tmp_path, sample_image_path):
    rc = cli.main(["parse", str(sample_image_path), "--out", str(tmp_path)])
    assert rc == 0
    data = json.loads((tmp_path / "board.json").read_text(encoding="utf-8"))
    if data["unmatched"]:
        assert (tmp_path / "unmatched.png").exists()
    else:
        assert not (tmp_path / "unmatched.png").exists()


def test_parse_writes_suspects_panel(tmp_path, sample_image_path):
    rc = cli.main(["parse", str(sample_image_path), "--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "suspects.png").exists()


def test_parse_writes_81_cell_tiles(tmp_path, sample_image_path):
    cli.main(["parse", str(sample_image_path), "--out", str(tmp_path)])
    tiles = sorted((tmp_path / "cells").glob("*.png"))
    assert len(tiles) == 81
    assert tiles[0].stem == "R1C1"


def test_parse_does_not_crash_when_library_missing(tmp_path, sample_image_path,
                                                   monkeypatch):
    """元素库为空时仍要产出棋盘与格子，只是全部进 unmatched"""
    import extract_board
    monkeypatch.setattr(extract_board, "ELEMENTS_JSON_DEFAULT",
                        tmp_path / "nope.json")
    rc = cli.main(["parse", str(sample_image_path), "--out", str(tmp_path)])
    assert rc == 0
    data = json.loads((tmp_path / "board.json").read_text(encoding="utf-8"))
    assert len(data["unmatched"]) == 81


def test_list_reports_library(tmp_path, capsys):
    rc = cli.main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "元素库" in out


def test_validate_command_reports_errors(tmp_path, capsys):
    bad = {"grid": 9}      # 缺一大堆字段
    f = tmp_path / "puzzle.json"
    f.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    rc = cli.main(["validate", str(f)])
    assert rc == 1
    assert "❌" in capsys.readouterr().out


def test_migrate_dry_run_leaves_file_untouched(tmp_path, capsys):
    f = tmp_path / "elements.json"
    f.write_text(json.dumps({"elements": {}}, ensure_ascii=False), encoding="utf-8")
    before = f.read_text(encoding="utf-8")
    rc = cli.main(["migrate", "--path", str(f), "--dry-run"])
    assert rc == 0
    assert f.read_text(encoding="utf-8") == before


def test_validate_missing_file_reports_emoji_and_returns_1(tmp_path, capsys):
    """puzzle 文件不存在时走 ❌ 提示 + rc=1，不抛裸 traceback。

    对齐 cmd_parse/cmd_add/cmd_calibrate 对缺图的处理；spec §8 要求
    validate 出错输出 ❌ 并以 1 退出，打错文件名看到 Python 堆栈不可接受。
    """
    rc = cli.main(["validate", str(tmp_path / "typo.json")])
    assert rc == 1
    out = capsys.readouterr().out
    assert "❌" in out


def test_main_prints_utf8_on_cp936_stream(monkeypatch, tmp_path):
    """stdout 声明为 cp936 时仍按 UTF-8 产出，不抛异常也不出乱码。

    Windows 控制台默认 cp936，旧代码直接 print 中文/emoji 会落成本地码页
    字节（emoji 更是直接 UnicodeEncodeError），而技能要求中文输出。
    中文半边用 list、emoji 半边用 validate（❌）分别锁住——list 的输出里
    没有任何 emoji，只跑它锁不住 emoji 那一半。
    """
    import io
    import sys

    def attach_cp936_stream():
        """每轮新建一条 cp936 流：上一轮 main() 已把它切成 utf-8，复用会失真"""
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp936", newline="", write_through=True)
        monkeypatch.setattr(sys, "stdout", stream)
        return raw, stream

    # —— 中文半边 ——
    raw, stream = attach_cp936_stream()
    rc = cli.main(["list"])
    assert rc == 0
    stream.flush()
    out = raw.getvalue().decode("utf-8")   # 必须是 UTF-8 字节，否则这里就炸
    assert "椅子" in out

    # —— emoji 半边 ——
    raw, stream = attach_cp936_stream()
    rc = cli.main(["validate", str(tmp_path / "nope.json")])
    assert rc == 1
    stream.flush()
    out = raw.getvalue().decode("utf-8")
    assert "❌" in out
