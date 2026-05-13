/**
 * 文件职责：提供管理端通用的 Markdown 渲染与安全清洗能力，供多个视图复用。
 */

const MARKDOWN_CODE_LANGUAGE_LABELS = {
    // 这里维护“代码块语言名 -> 展示标签”的映射，供代码块头部语言徽标使用。
    js: 'JavaScript',
    jsx: 'JSX',
    ts: 'TypeScript',
    tsx: 'TSX',
    json: 'JSON',
    bash: 'Bash',
    shell: 'Shell',
    sh: 'Shell',
    python: 'Python',
    py: 'Python',
    yaml: 'YAML',
    yml: 'YAML',
    html: 'HTML',
    css: 'CSS',
    md: 'Markdown',
    markdown: 'Markdown',
    mermaid: 'Mermaid',
    text: 'Text',
    plaintext: 'Text',
};

const MARKDOWN_SANITIZE_OPTIONS = {
    // 白名单只开放管理端实际需要的 Markdown 标签，减少攻击面。
    ALLOWED_TAGS: [
        'a', 'blockquote', 'br', 'code', 'del', 'details', 'div', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'hr', 'img', 'li', 'ol', 'p', 'pre', 'span', 'strong', 'summary', 'table', 'tbody', 'td', 'th', 'thead', 'tr', 'ul'
    ],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'class', 'data-language', 'data-mermaid-source', 'src', 'alt', 'title', 'width', 'height', 'align', 'open', 'loading', 'decoding', 'referrerpolicy'],
    FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form'],
    FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick', 'onmouseover', 'onfocus'],
    RETURN_DOM_FRAGMENT: true,
};

function normalizeMarkdownContent(content) {
    return String(content || '')
        // 兼容真实换行与被序列化成字符串字面量的“\n”。
        .replace(/\r\n/g, '\n')
        .replace(/\\n/g, '\n')
        // 最后统一收敛为 LF，避免后续正则与分行逻辑在不同平台行为不一致。
        .replace(/\r\n?/g, '\n');
}

function isProbablyMarkdown(content) {
    const normalized = normalizeMarkdownContent(content);
    // 这里不是严格 Markdown 语法解析，而是用启发式规则快速判断“是否值得进入 Markdown 渲染管线”。
    return /(^|\n)\s{0,3}(#{1,6}\s|>\s|[-*+]\s)|(\n|^)\s*\d+\.\s|(^|\n)\s*```|(^|\n)\|.+\|/m.test(normalized);
}

function escapeMarkdownHtml(text) {
    return String(text || '')
        // 所有 fallback 渲染路径都先做 HTML 转义，防止原始文本直接进入 innerHTML。
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function normalizeMarkdownLanguageName(language) {
    const normalized = String(language || '').trim().toLowerCase();
    if (!normalized) return 'text';
    // 限制语言名字符集，避免把奇怪 class 名直接拼进 DOM。
    return normalized.replace(/[^a-z0-9_-]/g, '') || 'text';
}

function getMarkdownLanguageLabel(language) {
    const normalized = normalizeMarkdownLanguageName(language);
    // 优先使用预定义标签；若没有映射，则退化为大写原语言名。
    return MARKDOWN_CODE_LANGUAGE_LABELS[normalized] || normalized.toUpperCase() || 'Text';
}

function getSafeMarkdownLinkHref(href) {
    const value = String(href || '').trim();
    // 仅放行 http(s)、站内绝对路径和锚点链接，避免 javascript: 等危险协议。
    if (/^https?:\/\//i.test(value) || value.startsWith('/') || value.startsWith('#')) {
        return value;
    }
    return '#';
}

function getSafeMarkdownImageSrc(src) {
    const value = String(src || '').trim();
    // 图片仅放行 http(s) 与站内相对路径，避免 data/javascript/blob 等协议带来的注入或追踪风险。
    if (/^https?:\/\//i.test(value) || value.startsWith('/') || value.startsWith('./') || value.startsWith('../')) {
        return value;
    }
    return '';
}

function highlightMarkdownCode(code, language) {
    const escaped = escapeMarkdownHtml(code);
    const normalizedLanguage = normalizeMarkdownLanguageName(language);

    if (normalizedLanguage === 'json') {
        // JSON 重点高亮 key / value / boolean / number，保持实现轻量而不引入大型高亮库。
        return escaped
            .replace(/("(?:[^"\\]|\\.)*")\s*:/g, '<span class="token token-key">$1</span><span class="token token-punctuation">:</span>')
            .replace(/:\s*("(?:[^"\\]|\\.)*")/g, ': <span class="token token-string">$1</span>')
            .replace(/\b(true|false|null)\b/g, '<span class="token token-boolean">$1</span>')
            .replace(/\b(-?\d+(?:\.\d+)?)\b/g, '<span class="token token-number">$1</span>');
    }

    if (['js', 'jsx', 'ts', 'tsx', 'javascript', 'typescript'].includes(normalizedLanguage)) {
        // JS / TS 采用最常用语法成分的正则高亮，目标是“可读性增强”而非完整语义解析。
        return escaped
            .replace(/\b(function|const|let|var|return|if|else|new|throw|class|async|await|import|from|export|default|try|catch)\b/g, '<span class="token token-keyword">$1</span>')
            .replace(/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/g, '<span class="token token-string">$1</span>')
            .replace(/\b(true|false|null|undefined)\b/g, '<span class="token token-boolean">$1</span>')
            .replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="token token-number">$1</span>')
            .replace(/\b([A-Za-z_$][\w$]*)\s*(?=\()/g, '<span class="token token-function">$1</span>');
    }

    if (['bash', 'shell', 'sh'].includes(normalizedLanguage)) {
        // Shell 场景重点强化命令名、flag 和字符串，提升安装命令 / 运维命令的扫读效率。
        const lines = escaped.split('\n');
        return lines
            .map((line) => {
                const commandMatch = line.match(/^(\s*)([A-Za-z0-9_./:-]+)(.*)$/);
                if (!commandMatch) return line;
                const [, indent, command, rest] = commandMatch;
                const highlightedRest = rest
                    .replace(/\s(-{1,2}[A-Za-z0-9_-]+)/g, ' <span class="token token-flag">$1</span>')
                    .replace(/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, '<span class="token token-string">$1</span>');
                return `${indent}<span class="token token-command">${command}</span>${highlightedRest}`;
            })
            .join('\n');
    }

    // Mermaid 图表源码不做语法高亮，直接保留为纯文本，避免破坏图定义。
    if (normalizedLanguage === 'mermaid') {
        return escaped;
    }

    // 未识别语言时保持纯转义文本，至少保证安全与可读。
    return escaped;
}

function buildMarkdownMermaidBlockHtml(code) {
    const normalizedCode = normalizeMarkdownContent(code).trim();
    const escapedCode = escapeMarkdownHtml(normalizedCode);
    return [
        '<div class="notification-md-mermaid-block" data-language="mermaid">',
        '<div class="notification-md-code-header">',
        `<span class="notification-md-code-lang">${escapeMarkdownHtml(getMarkdownLanguageLabel('mermaid'))}</span>`,
        '</div>',
        `<div class="notification-md-mermaid" data-mermaid-source="${escapedCode}">${escapedCode}</div>`,
        '</div>',
    ].join('');
}

function buildMarkdownCodeBlockHtml(code, language) {
    const normalizedLanguage = normalizeMarkdownLanguageName(language);
    if (normalizedLanguage === 'mermaid') {
        return buildMarkdownMermaidBlockHtml(code);
    }
    const languageClass = normalizedLanguage !== 'text' ? ` language-${normalizedLanguage}` : ' language-text';
    const languageLabel = getMarkdownLanguageLabel(normalizedLanguage);
    const highlightedCode = highlightMarkdownCode(code, normalizedLanguage);
    return [
        // 代码块外层统一使用 notification-md 的样式体系，便于通知页和文档页复用同一套 CSS。
        `<div class="notification-md-code-block${languageClass}">`,
        '<div class="notification-md-code-header">',
        `<span class="notification-md-code-lang">${escapeMarkdownHtml(languageLabel)}</span>`,
        '</div>',
        `<pre><code class="${languageClass.trim()}">${highlightedCode}</code></pre>`,
        '</div>',
    ].join('');
}

function extractInlineCodePlaceholders(text) {
    const placeholders = [];
    let output = '';
    const source = String(text || '');
    let index = 0;

    while (index < source.length) {
        const char = source[index];
        const prevChar = index > 0 ? source[index - 1] : '';
        if (char !== '`' || prevChar === '\\') {
            output += char;
            index += 1;
            continue;
        }

        let fenceLength = 1;
        while (source[index + fenceLength] === '`') {
            fenceLength += 1;
        }
        const fence = '`'.repeat(fenceLength);
        const searchStart = index + fenceLength;
        const closingIndex = source.indexOf(fence, searchStart);
        if (closingIndex === -1) {
            output += fence;
            index = searchStart;
            continue;
        }

        const code = source.slice(searchStart, closingIndex);
        if (!code) {
            output += fence + fence;
            index = closingIndex + fenceLength;
            continue;
        }

        // 先把内联 code 提取成占位符，避免后续粗粒度正则误伤其中内容。
        const placeholderIndex = placeholders.push(`<code>${escapeMarkdownHtml(code)}</code>`) - 1;
        output += `@@INLINE_CODE_${placeholderIndex}@@`;
        index = closingIndex + fenceLength;
    }

    return { output, placeholders };
}

function restoreInlineCodePlaceholders(text, placeholders) {
    return String(text || '').replace(/@@INLINE_CODE_(\d+)@@/g, (_, index) => placeholders[Number(index)] || '');
}

function applyInlineMarkdownTokens(text) {
    const extracted = extractInlineCodePlaceholders(text);
    let output = extracted.output;

    output = output.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) => {
        const safeHref = getSafeMarkdownLinkHref(href);
        return `<a href="${escapeMarkdownHtml(safeHref)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
    });
    // 这里按从“强语义到弱语义”的顺序处理，减少星号 / 下划线匹配互相影响。
    output = output.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    output = output.replace(/__([^_]+)__/g, '<strong>$1</strong>');
    output = output.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, '$1<em>$2</em>');
    output = output.replace(/(^|[^_])_([^_]+)_(?!_)/g, '$1<em>$2</em>');
    output = output.replace(/~~([^~]+)~~/g, '<del>$1</del>');

    return restoreInlineCodePlaceholders(output, extracted.placeholders);
}

function renderInlineMarkdownText(text) {
    return applyInlineMarkdownTokens(escapeMarkdownHtml(text));
}

function splitMarkdownTableCells(line) {
    const trimmed = String(line || '').trim().replace(/^\|/, '').replace(/\|$/, '');
    return trimmed.split('|').map((cell) => cell.trim());
}

function flushMarkdownParagraph(paragraphBuffer, htmlParts) {
    if (!paragraphBuffer.length) return [];
    const safeText = paragraphBuffer
        .map((line) => renderInlineMarkdownText(line))
        .join('<br />');
    htmlParts.push(`<p>${safeText}</p>`);
    return [];
}

function closeMarkdownList(listState, htmlParts) {
    if (!listState) return null;
    htmlParts.push(`</${listState}>`);
    return null;
}

function flushMarkdownBlockquote(blockquoteBuffer, htmlParts) {
    if (!blockquoteBuffer.length) return [];
    // 引用块递归复用同一渲染器，避免另外维护一套局部语法分支。
    const quoteHtml = fallbackRenderMarkdownHtml(blockquoteBuffer.join('\n'));
    htmlParts.push(`<blockquote>${quoteHtml}</blockquote>`);
    return [];
}

function flushMarkdownTable(tableHeader, tableRows, htmlParts) {
    if (!tableHeader) {
        return { tableHeader: null, tableRows: [] };
    }
    const headCells = tableHeader.map((cell) => `<th>${renderInlineMarkdownText(cell)}</th>`).join('');
    const bodyRows = tableRows
        .map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMarkdownText(cell)}</td>`).join('')}</tr>`)
        .join('');
    htmlParts.push(`<div class="notification-md-table-wrap"><table><thead><tr>${headCells}</tr></thead><tbody>${bodyRows}</tbody></table></div>`);
    return { tableHeader: null, tableRows: [] };
}

function fallbackRenderMarkdownHtml(md) {
    const normalized = normalizeMarkdownContent(md);
    const lines = normalized.split('\n');
    const htmlParts = [];
    let paragraphBuffer = [];
    let listState = null;
    let blockquoteBuffer = [];
    let codeFence = null;
    let tableHeader = null;
    let tableRows = [];

    for (let index = 0; index < lines.length; index += 1) {
        const rawLine = lines[index];
        const line = rawLine.trimEnd();
        const trimmed = line.trim();

        if (codeFence) {
            // 进入 fenced code block 后，直到遇到下一个 ``` 才退出，并原样保留中间内容。
            if (/^```/.test(trimmed)) {
                htmlParts.push(buildMarkdownCodeBlockHtml(codeFence.lines.join('\n'), codeFence.language));
                codeFence = null;
            } else {
                codeFence.lines.push(rawLine);
            }
            continue;
        }

        if (/^```/.test(trimmed)) {
            paragraphBuffer = flushMarkdownParagraph(paragraphBuffer, htmlParts);
            listState = closeMarkdownList(listState, htmlParts);
            blockquoteBuffer = flushMarkdownBlockquote(blockquoteBuffer, htmlParts);
            ({ tableHeader, tableRows } = flushMarkdownTable(tableHeader, tableRows, htmlParts));
            codeFence = {
                // ``` 后方内容作为语言名，例如 ```js。
                language: trimmed.slice(3).trim(),
                lines: [],
            };
            continue;
        }

        const tableSeparator = /^\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\|?$/.test(trimmed);
        if (tableHeader && !tableSeparator && trimmed.includes('|')) {
            // 表头建立后，连续的“含竖线行”都会被视作表格正文。
            tableRows.push(splitMarkdownTableCells(trimmed));
            continue;
        }
        if (tableHeader && (!trimmed || !trimmed.includes('|'))) {
            ({ tableHeader, tableRows } = flushMarkdownTable(tableHeader, tableRows, htmlParts));
        }

        if (!trimmed) {
            // 空行会触发段落 / 列表 / 引用 / 表格等块级结构的结算。
            paragraphBuffer = flushMarkdownParagraph(paragraphBuffer, htmlParts);
            listState = closeMarkdownList(listState, htmlParts);
            blockquoteBuffer = flushMarkdownBlockquote(blockquoteBuffer, htmlParts);
            ({ tableHeader, tableRows } = flushMarkdownTable(tableHeader, tableRows, htmlParts));
            continue;
        }

        const nextLine = String(lines[index + 1] || '').trim();
        if (!tableHeader && trimmed.includes('|') && /^\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\|?$/.test(nextLine)) {
            paragraphBuffer = flushMarkdownParagraph(paragraphBuffer, htmlParts);
            listState = closeMarkdownList(listState, htmlParts);
            blockquoteBuffer = flushMarkdownBlockquote(blockquoteBuffer, htmlParts);
            // 当前行认定为表头，下一行是分隔线，因此这里手动跳过一行。
            tableHeader = splitMarkdownTableCells(trimmed);
            tableRows = [];
            index += 1;
            continue;
        }

        const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
        if (heading) {
            paragraphBuffer = flushMarkdownParagraph(paragraphBuffer, htmlParts);
            listState = closeMarkdownList(listState, htmlParts);
            blockquoteBuffer = flushMarkdownBlockquote(blockquoteBuffer, htmlParts);
            ({ tableHeader, tableRows } = flushMarkdownTable(tableHeader, tableRows, htmlParts));
            const level = heading[1].length;
            htmlParts.push(`<h${level}>${renderInlineMarkdownText(heading[2])}</h${level}>`);
            continue;
        }

        if (/^---+$/.test(trimmed) || /^\*\*\*+$/.test(trimmed)) {
            paragraphBuffer = flushMarkdownParagraph(paragraphBuffer, htmlParts);
            listState = closeMarkdownList(listState, htmlParts);
            blockquoteBuffer = flushMarkdownBlockquote(blockquoteBuffer, htmlParts);
            ({ tableHeader, tableRows } = flushMarkdownTable(tableHeader, tableRows, htmlParts));
            htmlParts.push('<hr />');
            continue;
        }

        const quote = line.match(/^>\s?(.*)$/);
        if (quote) {
            // 相邻引用行会累积到同一 buffer，最终递归渲染为一个 blockquote。
            paragraphBuffer = flushMarkdownParagraph(paragraphBuffer, htmlParts);
            listState = closeMarkdownList(listState, htmlParts);
            ({ tableHeader, tableRows } = flushMarkdownTable(tableHeader, tableRows, htmlParts));
            blockquoteBuffer.push(quote[1]);
            continue;
        }
        blockquoteBuffer = flushMarkdownBlockquote(blockquoteBuffer, htmlParts);

        const unorderedItem = trimmed.match(/^[-*+]\s+(.+)$/);
        const orderedItem = trimmed.match(/^\d+\.\s+(.+)$/);
        const listType = unorderedItem ? 'ul' : orderedItem ? 'ol' : null;
        if (listType) {
            paragraphBuffer = flushMarkdownParagraph(paragraphBuffer, htmlParts);
            ({ tableHeader, tableRows } = flushMarkdownTable(tableHeader, tableRows, htmlParts));
            if (listState && listState !== listType) {
                listState = closeMarkdownList(listState, htmlParts);
            }
            if (!listState) {
                htmlParts.push(`<${listType}>`);
                listState = listType;
            }
            const listContent = unorderedItem ? unorderedItem[1] : orderedItem[1];
            htmlParts.push(`<li>${renderInlineMarkdownText(listContent)}</li>`);
            continue;
        }

        listState = closeMarkdownList(listState, htmlParts);
        ({ tableHeader, tableRows } = flushMarkdownTable(tableHeader, tableRows, htmlParts));
        // 兜底情况视为普通段落内容，延迟到 flushParagraph 时统一输出为 <p>。
        paragraphBuffer.push(line);
    }

    // 文件结束后把剩余 buffer 全部结算，避免最后一段内容丢失。
    paragraphBuffer = flushMarkdownParagraph(paragraphBuffer, htmlParts);
    listState = closeMarkdownList(listState, htmlParts);
    blockquoteBuffer = flushMarkdownBlockquote(blockquoteBuffer, htmlParts);
    ({ tableHeader, tableRows } = flushMarkdownTable(tableHeader, tableRows, htmlParts));

    if (codeFence) {
        // 若文档意外缺少结尾 ```，仍尽量把已收集内容渲染出来，而不是整体丢弃。
        htmlParts.push(buildMarkdownCodeBlockHtml(codeFence.lines.join('\n'), codeFence.language));
    }

    return htmlParts.join('');
}

const MARKDOWN_CALLOUT_META = {
    note: { label: 'Note', icon: '📝' },
    tip: { label: 'Tip', icon: '💡' },
    important: { label: 'Important', icon: '❗' },
    warning: { label: 'Warning', icon: '⚠️' },
    caution: { label: 'Caution', icon: '🚨' },
};

function enhanceMarkdownCalloutBlockquotes(sanitizedFragment) {
    sanitizedFragment.querySelectorAll('blockquote').forEach((blockquote) => {
        const firstChild = blockquote.firstElementChild;
        if (!firstChild || firstChild.tagName !== 'P') {
            return;
        }

        const firstTextNode = Array.from(firstChild.childNodes).find((node) => node.nodeType === Node.TEXT_NODE && String(node.textContent || '').trim());
        if (!firstTextNode) {
            return;
        }

        const originalText = String(firstTextNode.textContent || '');
        const match = originalText.match(/^\s*\[!([A-Z]+)\]\s*(.*)$/);
        if (!match) {
            return;
        }

        const calloutType = String(match[1] || '').trim().toLowerCase();
        const calloutMeta = MARKDOWN_CALLOUT_META[calloutType];
        if (!calloutMeta) {
            return;
        }

        const inlineTitle = String(match[2] || '').trim();
        blockquote.classList.add('notification-md-callout', `is-${calloutType}`);

        const header = document.createElement('div');
        header.className = 'notification-md-callout-header';

        const icon = document.createElement('span');
        icon.className = 'notification-md-callout-icon';
        icon.textContent = calloutMeta.icon;
        header.appendChild(icon);

        const title = document.createElement('span');
        title.className = 'notification-md-callout-title';
        title.textContent = inlineTitle || calloutMeta.label;
        header.appendChild(title);

        const nextText = originalText.replace(match[0], '').trimStart();
        if (nextText) {
            firstTextNode.textContent = nextText;
        } else {
            firstTextNode.parentNode.removeChild(firstTextNode);
        }

        if (!firstChild.childNodes.length) {
            firstChild.remove();
        }

        blockquote.insertBefore(header, blockquote.firstChild || null);
    });
}

function enhanceMarkdownFragment(sanitizedFragment) {
    sanitizedFragment.querySelectorAll('a[href]').forEach((link) => {
        const href = String(link.getAttribute('href') || '').trim();
        // 二次校验链接协议，即使 marked 解析出 <a>，也不允许危险 href 流入最终 DOM。
        if (!/^https?:\/\//i.test(href) && !href.startsWith('/') && !href.startsWith('#')) {
            link.setAttribute('href', '#');
        }
        link.setAttribute('target', '_blank');
        link.setAttribute('rel', 'noopener noreferrer');
    });

    sanitizedFragment.querySelectorAll('img[src]').forEach((img) => {
        const safeSrc = getSafeMarkdownImageSrc(img.getAttribute('src'));
        if (!safeSrc) {
            img.remove();
            return;
        }
        img.setAttribute('src', safeSrc);
        img.setAttribute('loading', 'lazy');
        img.setAttribute('decoding', 'async');
        img.setAttribute('referrerpolicy', 'no-referrer');
    });

    sanitizedFragment.querySelectorAll('table').forEach((table) => {
        // 自动为表格包一层横向滚动容器，避免窄屏下表格把布局撑爆。
        if (!table.parentElement || !table.parentElement.classList.contains('notification-md-table-wrap')) {
            const wrapper = document.createElement('div');
            wrapper.className = 'notification-md-table-wrap';
            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);
        }
    });

    enhanceMarkdownCalloutBlockquotes(sanitizedFragment);

    sanitizedFragment.querySelectorAll('details').forEach((detailsEl) => {
        detailsEl.classList.add('notification-md-details');
        const firstSummary = Array.from(detailsEl.children).find((child) => child.tagName === 'SUMMARY');
        if (firstSummary) {
            firstSummary.classList.add('notification-md-summary');
        } else {
            const summary = document.createElement('summary');
            summary.className = 'notification-md-summary';
            summary.textContent = '展开详情';
            detailsEl.insertBefore(summary, detailsEl.firstChild || null);
        }
    });

    sanitizedFragment.querySelectorAll('pre > code').forEach((codeEl) => {
        const originalClass = String(codeEl.getAttribute('class') || '');
        const languageMatch = originalClass.match(/language-([a-z0-9_-]+)/i);
        const language = normalizeMarkdownLanguageName(languageMatch ? languageMatch[1] : 'text');
        const rawCodeText = codeEl.textContent || '';
        const pre = codeEl.parentElement;

        if (language === 'mermaid') {
            const mermaidWrapper = document.createElement('div');
            mermaidWrapper.innerHTML = buildMarkdownMermaidBlockHtml(rawCodeText);
            pre.parentNode.replaceChild(mermaidWrapper.firstElementChild, pre);
            return;
        }

        const wrapper = document.createElement('div');
        wrapper.className = `notification-md-code-block language-${language}`;
        wrapper.setAttribute('data-language', language);

        const header = document.createElement('div');
        header.className = 'notification-md-code-header';

        const langChip = document.createElement('span');
        langChip.className = 'notification-md-code-lang';
        langChip.textContent = getMarkdownLanguageLabel(language);
        header.appendChild(langChip);

        // 把代码内容替换为轻量高亮结果，同时保留原本 <pre><code> 结构供样式复用。
        codeEl.className = `language-${language}`;
        codeEl.innerHTML = highlightMarkdownCode(rawCodeText, language);

        pre.parentNode.insertBefore(wrapper, pre);
        wrapper.appendChild(header);
        wrapper.appendChild(pre);
    });
}

function renderMarkdownToHtml(content) {
    const normalized = normalizeMarkdownContent(content);

    try {
        const marked = window.marked;
        const DOMPurify = window.DOMPurify;

        if (marked && DOMPurify) {
            const parseMarkdown = (md) => {
                // 优先适配 marked.parse 新接口，同时兼容老版本把 marked 作为函数调用的形式。
                if (typeof marked.parse === 'function') {
                    return marked.parse(md, { gfm: true, breaks: true });
                }
                if (typeof marked === 'function') {
                    return marked(md, { gfm: true, breaks: true });
                }
                throw new Error('marked parser unavailable');
            };

            const rawHtml = parseMarkdown(normalized);
            const sanitizedFragment = DOMPurify.sanitize(rawHtml, MARKDOWN_SANITIZE_OPTIONS);
            enhanceMarkdownFragment(sanitizedFragment);

            const container = document.createElement('div');
            container.appendChild(sanitizedFragment);
            return container.innerHTML;
        }
    } catch (e) {
        // 解析失败时回退到内置渲染器，保证页面仍然可读。
    }

    return fallbackRenderMarkdownHtml(normalized);
}

window.MarkdownRenderUtil = {
    // 暴露为全局工具对象，供通知页与文档页在无打包环境下直接复用。
    normalizeMarkdownContent,
    isProbablyMarkdown,
    renderMarkdownToHtml,
};
