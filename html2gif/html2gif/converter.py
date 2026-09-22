"""HTML 转 GIF 的核心转换逻辑。"""

from pathlib import Path
from typing import Callable, Sequence
from urllib.parse import urlparse

from PIL import Image


def resolve_source(source: str) -> str:
    """把输入源规范化为 Playwright 可打开的 URL。

    - http:// 与 https:// 原样返回；
    - 其它含协议的输入视为不支持，抛出 ValueError；
    - 其余按本地文件路径处理，返回 file:// URL。
    """
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        return source
    # Windows 盘符（如 D:/a.html）会被 urlparse 误判为协议，单字母协议按本地路径处理
    if parsed.scheme and len(parsed.scheme) > 1:
        raise ValueError(f"不支持的输入协议: {parsed.scheme}://（仅支持本地文件与 http/https）")

    path = Path(source).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"本地文件不存在: {path}")
    return path.resolve().as_uri()


def frame_count(duration: float, fps: float) -> int:
    """根据动画时长（秒）与帧率计算帧数；时长为 0 表示静态图（1 帧）。"""
    if duration < 0:
        raise ValueError(f"时长不能为负数: {duration}")
    if fps <= 0:
        raise ValueError(f"帧率必须为正数: {fps}")
    if duration == 0:
        return 1
    return max(1, round(duration * fps))


def frames_to_gif(
    frames: Sequence[Image.Image],
    output: str | Path,
    *,
    fps: float,
    loop: int = 0,
) -> Path:
    """把帧序列合成为 GIF 文件，返回输出路径。

    - fps: 帧率，决定每帧停留时长（1000/fps 毫秒）；
    - loop: 循环次数，0 表示无限循环。
    """
    if not frames:
        raise ValueError("帧序列不能为空")

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration_ms = round(1000 / fps)

    # GIF 最多 256 色，统一转为自适应调色板模式
    palette_frames = [frame.convert("P", palette=Image.Palette.ADAPTIVE) for frame in frames]
    first, rest = palette_frames[0], palette_frames[1:]
    first.save(
        output_path,
        save_all=True,
        append_images=rest,
        duration=duration_ms,
        loop=loop,
        optimize=True,
    )
    return output_path


def html_to_gif(
    source: str,
    output: str | Path,
    *,
    width: int = 1280,
    height: int = 800,
    duration: float = 3.0,
    fps: float = 10.0,
    full_page: bool = False,
    loop: int = 0,
    wait_until: str = "load",
    capture: Callable[..., list[Image.Image]] | None = None,
) -> Path:
    """把 HTML 页面（本地文件或 URL）转换为 GIF 动图，返回输出路径。

    capture 参数用于测试注入；默认使用 Playwright 截图实现。
    """
    url = resolve_source(source)
    frame_count(duration, fps)  # 先校验时长与帧率

    capture_fn = capture if capture is not None else capture_frames
    frames = capture_fn(
        url,
        width=width,
        height=height,
        duration=duration,
        fps=fps,
        full_page=full_page,
        wait_until=wait_until,
    )
    return frames_to_gif(frames, output, fps=fps, loop=loop)


def capture_frames(
    source: str,
    *,
    width: int = 1280,
    height: int = 800,
    duration: float = 3.0,
    fps: float = 10.0,
    full_page: bool = False,
    wait_until: str = "load",
) -> list[Image.Image]:
    """用无头 Chromium 打开页面，按 fps 在 duration 时间窗内截取动画帧。"""
    import io

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    n = frame_count(duration, fps)
    interval_ms = round(1000 / fps)
    frames: list[Image.Image] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(source, wait_until=wait_until)
                for i in range(n):
                    if i > 0:
                        page.wait_for_timeout(interval_ms)
                    shot = page.screenshot(full_page=full_page, type="png")
                    frames.append(Image.open(io.BytesIO(shot)).convert("RGB"))
            finally:
                browser.close()
    except PlaywrightError as exc:
        raise RuntimeError(
            f"页面渲染失败: {exc}\n"
            "若提示浏览器缺失，请先执行: python -m playwright install chromium"
        ) from exc

    return frames
