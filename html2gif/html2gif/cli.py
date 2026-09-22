"""html2gif 的命令行入口。"""

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

from html2gif.converter import html_to_gif


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="html2gif",
        description="将 HTML 页面（本地文件或 URL）转换为 GIF 动图",
    )
    parser.add_argument("source", help="HTML 文件路径或 http(s) URL")
    parser.add_argument("-o", "--output", help="输出 GIF 路径（默认与输入同名 .gif）")
    parser.add_argument("--width", type=int, default=1280, help="视口宽度（默认 1280）")
    parser.add_argument("--height", type=int, default=800, help="视口高度（默认 800）")
    parser.add_argument(
        "--duration", type=float, default=3.0,
        help="动画时长（秒），0 表示静态图（默认 3）",
    )
    parser.add_argument("--fps", type=float, default=10.0, help="帧率（默认 10）")
    parser.add_argument("--full-page", action="store_true", help="截取整页而不仅是视口")
    parser.add_argument("--loop", type=int, default=0, help="循环次数，0 为无限循环（默认 0）")
    parser.add_argument(
        "--wait-until", default="load",
        choices=["load", "domcontentloaded", "networkidle", "commit"],
        help="页面加载完成的判定（默认 load）",
    )
    return parser


def default_output(source: str) -> Path:
    """由输入源推导默认输出路径：取文件名（去查询串）后缀改为 .gif。"""
    name = Path(urlparse(source).path).name or "output"
    return Path(name).with_suffix(".gif")


def main(argv: list[str] | None = None) -> int:
    """命令行主入口，返回进程退出码。"""
    args = build_parser().parse_args(argv)
    output = Path(args.output) if args.output else default_output(args.source)

    try:
        result = html_to_gif(
            args.source,
            output,
            width=args.width,
            height=args.height,
            duration=args.duration,
            fps=args.fps,
            full_page=args.full_page,
            loop=args.loop,
            wait_until=args.wait_until,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    print(f"已生成: {result}")
    return 0
