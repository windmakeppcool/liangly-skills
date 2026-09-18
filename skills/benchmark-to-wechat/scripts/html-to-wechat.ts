#!/usr/bin/env node

/**
 * HTML 转微信友好格式转换器
 * 将 HTML 内容转换为 Markdown 或内联样式的 HTML，适合微信公众号编辑器
 *
 * 用法：
 *   node html-to-wechat.ts <input.html> [--output output.md]
 *   node html-to-wechat.ts --stdin [--output output.md]
 */

import * as fs from 'fs';
import * as path from 'path';

interface ConversionOptions {
  outputFormat: 'markdown' | 'html';
  preserveCodeBlocks: boolean;
  maxCodeBlockLines: number;
  linkPosition: 'inline' | 'footnote';
}

const defaultOptions: ConversionOptions = {
  outputFormat: 'markdown',
  preserveCodeBlocks: true,
  maxCodeBlockLines: 50,
  linkPosition: 'footnote'
};

/**
 * 转换 HTML 为 Markdown
 */
function htmlToMarkdown(html: string, options: ConversionOptions = defaultOptions): string {
  let markdown = html;
  const links: Array<{ text: string; url: string }> = [];

  // 移除 HTML 注释
  markdown = markdown.replace(/<!--[\s\S]*?-->/g, '');

  // 处理标题
  markdown = markdown.replace(/<h1[^>]*>(.*?)<\/h1>/gi, '# $1\n\n');
  markdown = markdown.replace(/<h2[^>]*>(.*?)<\/h2>/gi, '## $1\n\n');
  markdown = markdown.replace(/<h3[^>]*>(.*?)<\/h3>/gi, '### $1\n\n');
  markdown = markdown.replace(/<h4[^>]*>(.*?)<\/h4>/gi, '#### $1\n\n');
  markdown = markdown.replace(/<h5[^>]*>(.*?)<\/h5>/gi, '##### $1\n\n');
  markdown = markdown.replace(/<h6[^>]*>(.*?)<\/h6>/gi, '###### $1\n\n');

  // 处理加粗和斜体
  markdown = markdown.replace(/<(?:strong|b)>(.*?)<\/(?:strong|b)>/gi, '**$1**');
  markdown = markdown.replace(/<(?:em|i)>(.*?)<\/(?:em|i)>/gi, '*$1*');

  // 处理链接（提取到脚注）
  if (options.linkPosition === 'footnote') {
    let linkIndex = 0;
    markdown = markdown.replace(/<a[^>]*href="([^"]*)"[^>]*>(.*?)<\/a>/gi, (match, url, text) => {
      linkIndex++;
      links.push({ text, url });
      return `${text}[${linkIndex}]`;
    });
  } else {
    markdown = markdown.replace(/<a[^>]*href="([^"]*)"[^>]*>(.*?)<\/a>/gi, '[$2]($1)');
  }

  // 处理图片
  markdown = markdown.replace(/<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*\/?>/gi, '![$2]($1)');
  markdown = markdown.replace(/<img[^>]*src="([^"]*)"[^>]*\/?>/gi, '![图片]($1)');

  // 处理代码块
  if (options.preserveCodeBlocks) {
    // 处理 <pre><code> 块
    markdown = markdown.replace(/<pre[^>]*>\s*<code[^>]*>([\s\S]*?)<\/code>\s*<\/pre>/gi, (match, code) => {
      const lines = code.split('\n');
      const truncated = lines.length > options.maxCodeBlockLines
        ? lines.slice(0, options.maxCodeBlockLines).join('\n') + '\n// ... (省略 ' + (lines.length - options.maxCodeBlockLines) + ' 行)'
        : code;
      return '```\n' + truncated + '\n```\n\n';
    });

    // 处理单独的 <pre> 块
    markdown = markdown.replace(/<pre[^>]*>([\s\S]*?)<\/pre>/gi, (match, code) => {
      const lines = code.split('\n');
      const truncated = lines.length > options.maxCodeBlockLines
        ? lines.slice(0, options.maxCodeBlockLines).join('\n') + '\n// ... (省略 ' + (lines.length - options.maxCodeBlockLines) + ' 行)'
        : code;
      return '```\n' + truncated + '\n```\n\n';
    });

    // 处理行内代码
    markdown = markdown.replace(/<code[^>]*>(.*?)<\/code>/gi, '`$1`');
  } else {
    // 移除代码标签，只保留内容
    markdown = markdown.replace(/<pre[^>]*>([\s\S]*?)<\/pre>/gi, '[代码块]');
    markdown = markdown.replace(/<code[^>]*>(.*?)<\/code>/gi, '$1');
  }

  // 处理列表
  markdown = markdown.replace(/<ul[^>]*>([\s\S]*?)<\/ul>/gi, (match, content) => {
    return content.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, '- $1\n') + '\n';
  });

  markdown = markdown.replace(/<ol[^>]*>([\s\S]*?)<\/ol>/gi, (match, content) => {
    let index = 0;
    return content.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, () => {
      index++;
      return `${index}. $1\n`;
    }) + '\n';
  });

  // 处理引用块
  markdown = markdown.replace(/<blockquote[^>]*>([\s\S]*?)<\/blockquote>/gi, (match, content) => {
    return content.split('\n').map((line: string) => '> ' + line).join('\n') + '\n\n';
  });

  // 处理表格
  markdown = markdown.replace(/<table[^>]*>([\s\S]*?)<\/table>/gi, (match, tableContent) => {
    const rows: string[] = [];
    const trRegex = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
    let trMatch;

    while ((trMatch = trRegex.exec(tableContent)) !== null) {
      const cells: string[] = [];
      const cellRegex = /<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi;
      let cellMatch;

      while ((cellMatch = cellRegex.exec(trMatch[1])) !== null) {
        cells.push(cellMatch[1].trim());
      }

      if (cells.length > 0) {
        rows.push('| ' + cells.join(' | ') + ' |');
      }
    }

    if (rows.length > 0) {
      // 添加表头分隔行
      const headerSeparator = '| ' + rows[0].split('|').slice(1, -1).map(() => '---').join(' | ') + ' |';
      rows.splice(1, 0, headerSeparator);
    }

    return rows.join('\n') + '\n\n';
  });

  // 处理段落和换行
  markdown = markdown.replace(/<p[^>]*>([\s\S]*?)<\/p>/gi, '$1\n\n');
  markdown = markdown.replace(/<br\s*\/?>/gi, '\n');
  markdown = markdown.replace(/<hr\s*\/?>/gi, '---\n\n');

  // 移除其他 HTML 标签
  markdown = markdown.replace(/<[^>]+>/g, '');

  // 解码 HTML 实体
  markdown = decodeHtmlEntities(markdown);

  // 清理多余空行
  markdown = markdown.replace(/\n{3,}/g, '\n\n');

  // 添加链接脚注
  if (options.linkPosition === 'footnote' && links.length > 0) {
    markdown += '\n\n---\n\n**参考资料：**\n\n';
    links.forEach((link, index) => {
      markdown += `[${index + 1}] ${link.text}: ${link.url}\n`;
    });
  }

  return markdown.trim();
}

/**
 * 转换 HTML 为内联样式的 HTML（微信兼容）
 */
function htmlToInlineStyles(html: string): string {
  let result = html;

  // 添加内联样式到常见标签
  const styleMap: Record<string, string> = {
    'h1': 'font-size: 24px; font-weight: bold; margin: 20px 0 10px 0; color: #333;',
    'h2': 'font-size: 20px; font-weight: bold; margin: 18px 0 8px 0; color: #333;',
    'h3': 'font-size: 18px; font-weight: bold; margin: 16px 0 6px 0; color: #333;',
    'p': 'font-size: 16px; line-height: 1.8; margin: 10px 0; color: #333;',
    'pre': 'background-color: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; font-family: Consolas, Monaco, "Courier New", monospace; font-size: 14px; line-height: 1.6;',
    'code': 'background-color: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: Consolas, Monaco, "Courier New", monospace; font-size: 14px;',
    'blockquote': 'border-left: 4px solid #ddd; padding-left: 12px; margin: 10px 0; color: #666;',
    'table': 'border-collapse: collapse; width: 100%; margin: 10px 0;',
    'th': 'border: 1px solid #ddd; padding: 8px; background-color: #f5f5f5; text-align: left;',
    'td': 'border: 1px solid #ddd; padding: 8px;',
    'a': 'color: #576b95; text-decoration: none;',
    'ul': 'margin: 10px 0; padding-left: 20px;',
    'ol': 'margin: 10px 0; padding-left: 20px;',
    'li': 'font-size: 16px; line-height: 1.8; margin: 5px 0;',
    'strong': 'font-weight: bold;',
    'em': 'font-style: italic;'
  };

  // 为标签添加内联样式
  for (const [tag, style] of Object.entries(styleMap)) {
    const regex = new RegExp(`<${tag}(\\s[^>]*)?>`, 'gi');
    result = result.replace(regex, (match, attrs) => {
      // 如果已经有 style 属性，追加；否则添加
      if (attrs && attrs.includes('style=')) {
        return match.replace(/style="([^"]*)"/, `style="$1 ${style}"`);
      }
      return `<${tag} style="${style}"${attrs || ''}>`;
    });
  }

  return result;
}

/**
 * 解码 HTML 实体
 */
function decodeHtmlEntities(text: string): string {
  const entities: Record<string, string> = {
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
    '&quot;': '"',
    '&#39;': "'",
    '&nbsp;': ' ',
    '&copy;': '©',
    '&reg;': '®',
    '&trade;': '™'
  };

  let result = text;
  for (const [entity, char] of Object.entries(entities)) {
    result = result.replace(new RegExp(entity, 'g'), char);
  }

  return result;
}

/**
 * 主函数
 */
function main() {
  const args = process.argv.slice(2);

  if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
    console.log(`
HTML 转微信友好格式转换器

用法：
  node html-to-wechat.ts <input.html> [options]
  cat input.html | node html-to-wechat.ts --stdin [options]

选项：
  --output <file>    输出文件路径（默认：stdout）
  --format <type>    输出格式：markdown 或 html（默认：markdown）
  --stdin            从标准输入读取
  --help, -h         显示帮助信息

示例：
  node html-to-wechat.ts report.html --output report.md
  node html-to-wechat.ts report.html --format html --output report-wechat.html
`);
    process.exit(0);
  }

  const options: ConversionOptions = { ...defaultOptions };

  // 解析参数
  let inputFile: string | null = null;
  let outputFile: string | null = null;
  let useStdin = false;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--output' && i + 1 < args.length) {
      outputFile = args[i + 1];
      i++;
    } else if (args[i] === '--format' && i + 1 < args.length) {
      options.outputFormat = args[i + 1] as 'markdown' | 'html';
      i++;
    } else if (args[i] === '--stdin') {
      useStdin = true;
    } else if (!args[i].startsWith('-')) {
      inputFile = args[i];
    }
  }

  // 读取输入
  let inputHtml: string;

  if (useStdin) {
    inputHtml = fs.readFileSync(0, 'utf-8');
  } else if (inputFile) {
    if (!fs.existsSync(inputFile)) {
      console.error(`错误：文件不存在: ${inputFile}`);
      process.exit(1);
    }
    inputHtml = fs.readFileSync(inputFile, 'utf-8');
  } else {
    console.error('错误：请指定输入文件或使用 --stdin');
    process.exit(1);
  }

  // 转换
  let output: string;

  if (options.outputFormat === 'markdown') {
    output = htmlToMarkdown(inputHtml, options);
  } else {
    output = htmlToInlineStyles(inputHtml);
  }

  // 输出
  if (outputFile) {
    fs.writeFileSync(outputFile, output, 'utf-8');
    console.log(`✅ 已保存到: ${outputFile}`);
  } else {
    console.log(output);
  }
}

// 如果是直接运行（而非导入）
if (require.main === module) {
  main();
}

export { htmlToMarkdown, htmlToInlineStyles, ConversionOptions };
