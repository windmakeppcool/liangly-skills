"""cli 模块的单元测试。"""

from pathlib import Path

import pytest

from html2gif.cli import build_parser, main


class TestBuildParser:
    """测试命令行参数解析。"""

    def test_defaults(self) -> None:
        """默认值：1280x800、3 秒、10fps、无限循环。"""
        args = build_parser().parse_args(["page.html"])
        assert args.source == "page.html"
        assert args.width == 1280
        assert args.height == 800
        assert args.duration == 3.0
        assert args.fps == 10.0
        assert args.full_page is False
        assert args.loop == 0
        assert args.wait_until == "load"

    def test_custom_options(self) -> None:
        """自定义选项应正确解析。"""
        args = build_parser().parse_args(
            [
                "page.html",
                "-o", "out.gif",
                "--width", "640",
                "--height", "480",
                "--duration", "2.5",
                "--fps", "8",
                "--full-page",
                "--loop", "1",
                "--wait-until", "networkidle",
            ]
        )
        assert args.output == "out.gif"
        assert args.width == 640
        assert args.height == 480
        assert args.duration == 2.5
        assert args.fps == 8
        assert args.full_page is True
        assert args.loop == 1
        assert args.wait_until == "networkidle"

    def test_default_output_derived_from_input(self) -> None:
        """未指定 -o 时，输出名应为输入名加 .gif。"""
        args = build_parser().parse_args(["demo.html"])
        assert args.output is None  # 由 main 在运行时推导


class TestMain:
    """测试命令行入口。"""

    def test_success_returns_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """转换成功返回退出码 0。"""
        html = tmp_path / "a.html"
        html.write_text("<html></html>", encoding="utf-8")
        monkeypatch.setattr(
            "html2gif.cli.html_to_gif",
            lambda *a, **k: tmp_path / "a.gif",
        )
        assert main([str(html)]) == 0

    def test_missing_file_returns_one(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """输入文件不存在时返回退出码 1 并输出中文错误。"""
        monkeypatch.chdir(Path("D:/tmp/html2gif"))
        assert main(["不存在的文件.html"]) == 1
        err = capsys.readouterr().err
        assert "不存在" in err

    def test_invalid_params_return_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """非法参数（如负时长）返回退出码 1 并输出错误。"""
        html = tmp_path / "a.html"
        html.write_text("<html></html>", encoding="utf-8")
        assert main([str(html), "--duration", "-1"]) == 1
        err = capsys.readouterr().err
        assert err.strip() != ""

    def test_default_output_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """未指定输出时应生成与输入同名的 .gif。"""
        html = tmp_path / "demo.html"
        html.write_text("<html></html>", encoding="utf-8")
        captured: dict[str, Path] = {}

        def fake_html_to_gif(source: str, output: str | Path, **kwargs: object) -> Path:
            captured["output"] = Path(output)
            return Path(output)

        monkeypatch.setattr("html2gif.cli.html_to_gif", fake_html_to_gif)
        main([str(html)])
        assert captured["output"].name == "demo.gif"
