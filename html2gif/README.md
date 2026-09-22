# html2gif

将 HTML 页面（本地文件或 http/https URL）转换为 GIF 动图的 Python 命令行工具。

用无头 Chromium（Playwright）渲染页面并按时间轴截取多帧，可捕捉 CSS/JS/Canvas 动画，再由 Pillow 合成 GIF。

## 安装

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## 使用

```bash
# 本地 HTML → GIF（默认 1280x800、录制 3 秒、10fps、无限循环）
python -m html2gif page.html

# 指定输出与参数
python -m html2gif page.html -o demo.gif --width 960 --height 540 --duration 3 --fps 10

# 转换网页 URL，截取整页
python -m html2gif https://example.com --full-page -o example.gif

# 静态截图（单帧 GIF）
python -m html2gif page.html --duration 0 -o still.gif
```

### 参数一览

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `source` | （必填） | HTML 文件路径或 http(s) URL |
| `-o, --output` | 与输入同名 `.gif` | 输出 GIF 路径 |
| `--width` | 1280 | 视口宽度 |
| `--height` | 800 | 视口高度 |
| `--duration` | 3.0 | 动画时长（秒），0 表示静态单帧 |
| `--fps` | 10.0 | 帧率（每秒截取帧数） |
| `--full-page` | 关 | 截取整页而不仅是视口 |
| `--loop` | 0 | 循环次数，0 为无限循环 |
| `--wait-until` | load | 页面加载判定：load / domcontentloaded / networkidle / commit |

### 作为库调用

```python
from html2gif.converter import html_to_gif

html_to_gif("page.html", "out.gif", width=960, height=540, duration=3.0, fps=10.0)
```

## 运行测试

```bash
python -m pytest tests/
```

单元测试不依赖浏览器；`tests/test_e2e.py` 会启动真实无头 Chromium 验证端到端转换。

## 说明

- GIF 每帧时长为 `1000/fps` 毫秒（受 GIF 格式 1/100 秒精度限制）。
- 帧数 = `duration × fps`（四舍五入，至少 1 帧）。时长越长、帧率越高，文件越大。
- 页面加载失败、本地文件不存在、协议不支持等情况会输出中文错误并以退出码 1 结束。
