"""端到端测试：用真实无头浏览器渲染 HTML 并生成 GIF。

需要已安装 Playwright 的 Chromium（python -m playwright install chromium）。
"""

from pathlib import Path

import pytest

from html2gif.converter import capture_frames, html_to_gif

ANIMATED_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body { margin: 0; }
#box { width: 50px; height: 50px; background: red;
       animation: move 1s linear infinite alternate; }
@keyframes move { from { transform: translateX(0); } to { transform: translateX(150px); } }
</style></head>
<body><div id="box"></div></body></html>
"""


@pytest.fixture
def animated_page(tmp_path: Path) -> str:
    """生成一个带 CSS 动画的本地页面，返回路径。"""
    html = tmp_path / "anim.html"
    html.write_text(ANIMATED_HTML, encoding="utf-8")
    return str(html)


class TestCaptureFrames:
    """测试 Playwright 截帧。"""

    def test_frame_count_and_size(self, animated_page: str) -> None:
        """0.5 秒、4fps 应截取 2 帧，尺寸等于视口。"""
        frames = capture_frames(
            animated_page,
            width=200,
            height=100,
            duration=0.5,
            fps=4.0,
        )
        assert len(frames) == 2
        assert all(f.size == (200, 100) for f in frames)

    def test_animation_changes_pixels(self, animated_page: str) -> None:
        """动画页面的多帧内容应有差异（证明截到的是动态画面）。"""
        frames = capture_frames(
            animated_page,
            width=200,
            height=100,
            duration=1.0,
            fps=4.0,
        )
        assert not all(
            frames[0].tobytes() == frame.tobytes() for frame in frames[1:]
        ), "各帧完全相同，动画未被捕获"


class TestEndToEnd:
    """端到端：HTML 文件 → GIF 文件。"""

    def test_html_file_to_animated_gif(self, animated_page: str, tmp_path: Path) -> None:
        """本地动画 HTML 应生成多帧 GIF，且帧内容有差异。"""
        out = tmp_path / "anim.gif"
        result = html_to_gif(
            animated_page,
            out,
            width=200,
            height=100,
            duration=1.0,
            fps=4.0,
        )
        assert result == out and out.exists()

        from PIL import Image

        with Image.open(out) as gif:
            assert gif.n_frames == 4
            gif.seek(0)
            first = gif.convert("RGB").tobytes()
            gif.seek(1)
            second = gif.convert("RGB").tobytes()
            assert first != second, "GIF 各帧完全相同，动画未被捕获"

    def test_static_single_frame(self, animated_page: str, tmp_path: Path) -> None:
        """duration=0 应输出单帧静态 GIF。"""
        out = tmp_path / "static.gif"
        html_to_gif(animated_page, out, width=200, height=100, duration=0.0, fps=10.0)
        from PIL import Image

        with Image.open(out) as gif:
            assert gif.n_frames == 1
