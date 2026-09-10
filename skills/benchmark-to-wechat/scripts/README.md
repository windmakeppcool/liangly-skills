# HTML 转微信格式工具

## 快速开始

### 前置要求

确保已安装 Node.js 和 TypeScript：

```bash
# 检查 Node.js 版本
node --version

# 安装 ts-node（如果没有）
npm install -g ts-node typescript
```

### 使用方法

#### 1. 转换 HTML 为 Markdown（推荐）

```bash
ts-node skills/benchmark-to-wechat/scripts/html-to-wechat.ts input.html --output output.md
```

#### 2. 转换 HTML 为内联样式的 HTML

```bash
ts-node skills/benchmark-to-wechat/scripts/html-to-wechat.ts input.html --format html --output output-wechat.html
```

#### 3. 从标准输入读取

```bash
cat input.html | ts-node skills/benchmark-to-wechat/scripts/html-to-wechat.ts --stdin --output output.md
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<input.html>` | 输入的 HTML 文件路径 | - |
| `--output <file>` | 输出文件路径 | stdout |
| `--format <type>` | 输出格式：`markdown` 或 `html` | `markdown` |
| `--stdin` | 从标准输入读取 | false |
| `--help, -h` | 显示帮助信息 | - |

## 转换规则

### Markdown 格式

- `<h1>` - `<h6>` → `#` - `######`
- `<strong>`, `<b>` → `**text**`
- `<em>`, `<i>` → `*text*`
- `<a href="...">` → `[text][N]`（脚注形式）
- `<img src="..." alt="...">` → `![alt](src)`
- `<pre><code>` → ` ``` ` 代码块（超过 50 行自动截断）
- `<code>` → `` `code` ``
- `<table>` → Markdown 表格
- `<blockquote>` → `> quote`
- `<ul>`, `<ol>` → `- item` 或 `1. item`

### HTML 格式（内联样式）

自动为标签添加内联样式，确保在微信公众号编辑器中正常显示：

- 字体大小：14-24px
- 行高：1.6-1.8
- 代码块背景：#f5f5f5
- 链接颜色：#576b95（微信风格）

## 常见问题

### Q: 为什么代码块被截断了？

微信公众号对长代码块支持不好，超过 50 行的代码会自动截断并标注省略行数。

### Q: 链接为什么变成脚注了？

微信公众号不支持超链接跳转，所以将链接提取到文末脚注，读者可以手动复制访问。

### Q: 图片怎么处理？

脚本会转换 `<img>` 为 Markdown 图片语法，但微信公众号需要手动上传图片。建议：

1. 先转换为 Markdown
2. 在微信编辑器中手动插入图片
3. 替换 Markdown 中的图片链接

## 集成到 benchmark-to-wechat 技能

在使用 `benchmark-to-wechat` 技能时，如果评测报告包含 HTML，代理会自动调用此脚本进行转换。

## 示例

### 输入 HTML

```html
<h2>测试结果</h2>
<p>模型回答如下：</p>
<pre><code>function hello() {
  console.log("Hello, World!");
}
</code></pre>
<p>详见 <a href="https://example.com">文档</a></p>
```

### 输出 Markdown

```markdown
## 测试结果

模型回答如下：

```
function hello() {
  console.log("Hello, World!");
}
```

详见 [文档][1]

---

**参考资料：**

[1] 文档: https://example.com
```
