"""converter 模块的单元测试。"""

from pathlib import Path

import pytest

from html2gif.converter import frame_count, resolve_source


class TestResolveSource:
    """测试输入源解析：本地路径转 file:// URL，网络 URL 原样保留。"""

    def test_http_url_unchanged(self) -> None:
        """http:// URL 应原样返回。"""
        assert resolve_source("http://example.com/page.html") == "http://example.com/page.html"

    def test_https_url_unchanged(self) -> None:
        """https:// URL 应原样返回。"""
        assert resolve_source("https://example.com/page.html") == "https://example.com/page.html"

    def test_local_file_to_file_url(self, tmp_path: Path) -> None:
        """本地 HTML 文件应转换为 file:// URL（绝对路径）。"""
        html = tmp_path / "demo.html"
        html.write_text("<html></html>", encoding="utf-8")
        result = resolve_source(str(html))
        assert result.startswith("file://")
        assert result.endswith("demo.html")

    def test_relative_path_resolved_to_absolute(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """相对路径应基于当前工作目录解析为绝对路径。"""
        html = tmp_path / "page.html"
        html.write_text("<html></html>", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        result = resolve_source("page.html")
        assert result.startswith("file://")
        assert Path(html).as_posix() in result.replace("\\", "/")

    def test_missing_local_file_raises(self) -> None:
        """本地文件不存在时应抛出 FileNotFoundError。"""
        with pytest.raises(FileNotFoundError):
            resolve_source("D:/不存在的目录/nope.html")

    def test_unsupported_scheme_raises(self) -> None:
        """不支持的协议（如 ftp://）应抛出 ValueError。"""
        with pytest.raises(ValueError):
            resolve_source("ftp://example.com/a.html")


class TestFrameCount:
    """测试帧数计算。"""

    def test_typical_duration(self) -> None:
        """3 秒、10 fps 应得 30 帧。"""
        assert frame_count(duration=3.0, fps=10.0) == 30

    def test_zero_duration_gives_single_frame(self) -> None:
        """时长为 0 表示静态图，只有 1 帧。"""
        assert frame_count(duration=0.0, fps=10.0) == 1

    def test_fractional_result_rounds(self) -> None:
        """帧数不足 1 时至少输出 1 帧；0.5*3=1.5 取四舍五入。"""
        assert frame_count(duration=0.5, fps=3.0) == 2

    def test_negative_duration_raises(self) -> None:
        """负时长应抛出 ValueError。"""
        with pytest.raises(ValueError):
            frame_count(duration=-1.0, fps=10.0)

    def test_non_positive_fps_raises(self) -> None:
        """帧率必须为正数。"""
        with pytest.raises(ValueError):
            frame_count(duration=1.0, fps=0.0)


class TestFramesToGif:
    """测试帧序列合成 GIF 文件。"""

    def _make_frames(self, n: int, size: tuple[int, int] = (40, 30)):
        """生成 n 张颜色渐变的测试帧。"""
        from PIL import Image

        return [
            Image.new("RGB", size, (i * 20 % 256, 100, 200))
            for i in range(n)
        ]

    def test_writes_gif_with_all_frames(self, tmp_path: Path) -> None:
        """5 帧输入应输出含 5 帧的 GIF。"""
        from PIL import Image

        from html2gif.converter import frames_to_gif

        out = tmp_path / "out.gif"
        frames_to_gif(self._make_frames(5), out, fps=10.0, loop=0)
        with Image.open(out) as gif:
            assert gif.n_frames == 5
            assert gif.is_animated

    def test_frame_size_preserved(self, tmp_path: Path) -> None:
        """GIF 尺寸应与输入帧一致。"""
        from PIL import Image

        from html2gif.converter import frames_to_gif

        out = tmp_path / "out.gif"
        frames_to_gif(self._make_frames(2, size=(120, 80)), out, fps=5.0, loop=0)
        with Image.open(out) as gif:
            assert gif.size == (120, 80)

    def test_frame_duration_from_fps(self, tmp_path: Path) -> None:
        """每帧时长应为 1000/fps 毫秒（10 fps → 100ms）。"""
        from PIL import Image

        from html2gif.converter import frames_to_gif

        out = tmp_path / "out.gif"
        frames_to_gif(self._make_frames(3), out, fps=10.0, loop=0)
        with Image.open(out) as gif:
            assert gif.info.get("duration") == 100

    def test_loop_count_written(self, tmp_path: Path) -> None:
        """循环次数应写入 GIF 元数据（0 = 无限循环）。"""
        from PIL import Image

        from html2gif.converter import frames_to_gif

        out = tmp_path / "out.gif"
        frames_to_gif(self._make_frames(2), out, fps=10.0, loop=3)
        with Image.open(out) as gif:
            assert gif.info.get("loop") == 3

    def test_single_frame_gif(self, tmp_path: Path) -> None:
        """单帧输入应生成单帧 GIF（静态图）。"""
        from PIL import Image

        from html2gif.converter import frames_to_gif

        out = tmp_path / "static.gif"
        frames_to_gif(self._make_frames(1), out, fps=10.0, loop=0)
        with Image.open(out) as gif:
            assert gif.n_frames == 1

    def test_empty_frames_raises(self, tmp_path: Path) -> None:
        """空帧序列应抛出 ValueError。"""
        from html2gif.converter import frames_to_gif

        with pytest.raises(ValueError):
            frames_to_gif([], tmp_path / "x.gif", fps=10.0, loop=0)

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        """输出路径的父目录不存在时应自动创建。"""
        from html2gif.converter import frames_to_gif

        out = tmp_path / "a" / "b" / "out.gif"
        frames_to_gif(self._make_frames(2), out, fps=10.0, loop=0)
        assert out.exists()


class TestHtmlToGif:
    """测试主入口 html_to_gif 的编排逻辑（注入假截图函数，不依赖浏览器）。"""

    def test_writes_gif_from_captured_frames(self, tmp_path: Path) -> None:
        """编排函数应把截图函数返回的帧写为 GIF。"""
        from PIL import Image

        from html2gif.converter import html_to_gif

        fake_frames = [
            Image.new("RGB", (50, 40), (i * 30 % 256, 0, 255))
            for i in range(4)
        ]

        def fake_capture(source: str, **kwargs: object) -> list:
            return fake_frames

        out = tmp_path / "result.gif"
        result = html_to_gif(
            "http://example.com",
            out,
            duration=2.0,
            fps=2.0,
            capture=fake_capture,
        )
        assert result == out
        from PIL import Image

        with Image.open(out) as gif:
            assert gif.n_frames == 4
            assert gif.size == (50, 40)

    def test_resolves_local_source_before_capture(self, tmp_path: Path) -> None:
        """本地文件应先解析为 file:// URL 再交给截图函数。"""
        from PIL import Image

        from html2gif.converter import html_to_gif

        html = tmp_path / "p.html"
        html.write_text("<html></html>", encoding="utf-8")
        seen: list[str] = []

        def fake_capture(source: str, **kwargs: object) -> list:
            seen.append(source)
            return [Image.new("RGB", (10, 10), (255, 0, 0))]

        html_to_gif(str(html), tmp_path / "o.gif", duration=0.0, fps=10.0, capture=fake_capture)
        assert seen and seen[0].startswith("file://")

    def test_propagates_missing_file_error(self) -> None:
        """输入文件不存在时应抛出 FileNotFoundError。"""
        from html2gif.converter import html_to_gif

        with pytest.raises(FileNotFoundError):
            html_to_gif(
                "D:/不存在/nope.html",
                "out.gif",
                capture=lambda *a, **k: [],
            )
