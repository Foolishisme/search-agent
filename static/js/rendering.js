export function initRichRendering() {
    if (window.mermaid) {
        window.mermaid.initialize({
            startOnLoad: false,
            securityLevel: 'strict',
            theme: 'neutral',
        });
    }
}

export function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;');
}

export function encodeCopyValue(value) {
    return encodeURIComponent(value || '');
}

export async function copyTextToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
    }

    const helper = document.createElement('textarea');
    helper.value = text;
    helper.setAttribute('readonly', '');
    helper.style.position = 'fixed';
    helper.style.opacity = '0';
    helper.style.pointerEvents = 'none';
    document.body.appendChild(helper);
    helper.focus();
    helper.select();
    const succeeded = document.execCommand('copy');
    document.body.removeChild(helper);
    if (!succeeded) {
        throw new Error('复制失败，请检查剪贴板权限');
    }
}

export function bindCopyButtons(container, { setStatus, setError }) {
    if (!container) {
        return;
    }
    container.querySelectorAll('.copy-message').forEach((button) => {
        if (button.dataset.bound === 'true') {
            return;
        }
        button.dataset.bound = 'true';
        button.addEventListener('click', async () => {
            const rawText = decodeURIComponent(button.dataset.copyText || '');
            try {
                await copyTextToClipboard(rawText);
                setStatus('已复制到剪贴板');
                setError('');
            } catch (error) {
                setError(error.message || '复制失败，请检查剪贴板权限');
            }
        });
    });
}

export function buildExpandableText(text, className = '') {
    const wrapper = document.createElement('div');
    const body = document.createElement('div');
    body.className = `clamped-text ${className}`.trim();
    body.textContent = text || '暂无摘要';
    wrapper.appendChild(body);

    if ((text || '').length > 88) {
        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'text-toggle';
        toggle.textContent = '展开';
        toggle.addEventListener('click', () => {
            const expanded = body.classList.toggle('expanded');
            toggle.textContent = expanded ? '收起' : '展开';
        });
        wrapper.appendChild(toggle);
    }

    return wrapper;
}

export function renderMarkdown(markdownText) {
    if (!markdownText) {
        return '<p class="placeholder">暂无答案。</p>';
    }
    if (window.marked && window.DOMPurify) {
        window.marked.setOptions({ gfm: true, breaks: false });
        return window.DOMPurify.sanitize(window.marked.parse(markdownText));
    }
    return `<p>${escapeHtml(markdownText).replaceAll('\n', '<br />')}</p>`;
}

export function getSafeHttpUrl(rawUrl) {
    const normalized = String(rawUrl || '').trim();
    if (!normalized) {
        return null;
    }
    try {
        const parsed = new URL(normalized);
        if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
            return parsed.toString();
        }
    } catch {
        return null;
    }
    return null;
}

function createSafeLink(url) {
    const safeUrl = getSafeHttpUrl(url);
    const link = document.createElement('a');
    link.href = safeUrl || '#';
    link.textContent = safeUrl || 'Invalid or non-HTTP(S) link';
    if (safeUrl) {
        link.target = '_blank';
        link.rel = 'noreferrer';
    }
    return link;
}

async function renderMermaidIn(container) {
    if (!container || !window.mermaid) {
        return;
    }

    const blocks = Array.from(container.querySelectorAll('pre code.language-mermaid, pre code.lang-mermaid'));
    if (!blocks.length) {
        return;
    }

    blocks.forEach((block, index) => {
        const pre = block.closest('pre');
        if (!pre) {
            return;
        }
        const chart = document.createElement('div');
        chart.className = 'mermaid';
        chart.id = `mermaid-${Date.now()}-${index}`;
        chart.textContent = block.textContent || '';
        pre.replaceWith(chart);
    });

    await window.mermaid.run({
        nodes: Array.from(container.querySelectorAll('.mermaid')),
        suppressErrors: true,
    });
}

function sanitizeSvgMarkup(svgText) {
    if (!svgText || !window.DOMPurify) {
        return '';
    }

    const sanitized = window.DOMPurify.sanitize(svgText, {
        USE_PROFILES: { svg: true, svgFilters: true },
        FORBID_TAGS: ['script', 'foreignObject', 'iframe', 'object', 'embed'],
        FORBID_ATTR: ['onload', 'onclick', 'onerror', 'onmouseover', 'onfocus'],
    }).trim();

    if (!sanitized) {
        return '';
    }

    const parser = new DOMParser();
    const doc = parser.parseFromString(sanitized, 'image/svg+xml');
    if (doc.querySelector('parsererror')) {
        return '';
    }

    const svg = doc.documentElement;
    if (!svg || svg.tagName.toLowerCase() !== 'svg') {
        return '';
    }

    const blockedTags = ['script', 'foreignobject', 'iframe', 'object', 'embed'];
    if (blockedTags.some((tag) => svg.querySelector(tag))) {
        return '';
    }

    const nodes = [svg, ...svg.querySelectorAll('*')];
    nodes.forEach((node) => {
        Array.from(node.attributes).forEach((attribute) => {
            const name = attribute.name.toLowerCase();
            const value = attribute.value.trim().toLowerCase();
            if (name.startsWith('on')) {
                node.removeAttribute(attribute.name);
                return;
            }
            if ((name === 'href' || name === 'xlink:href') && value.startsWith('javascript:')) {
                node.removeAttribute(attribute.name);
            }
        });
    });

    return svg.outerHTML;
}

function renderSvgIn(container) {
    if (!container) {
        return;
    }

    const blocks = Array.from(container.querySelectorAll('pre code.language-svg, pre code.lang-svg'));
    if (!blocks.length) {
        return;
    }

    blocks.forEach((block) => {
        const pre = block.closest('pre');
        if (!pre) {
            return;
        }

        const svgMarkup = sanitizeSvgMarkup(block.textContent || '');
        const card = document.createElement('div');
        card.className = 'svg-card';

        if (!svgMarkup) {
            card.innerHTML = `
                <div class="svg-card-head">
                    <span class="svg-card-title">SVG 图形</span>
                    <span class="svg-card-meta">渲染失败</span>
                </div>
                <div class="svg-error">SVG 内容无效或未通过安全校验。</div>
            `;
            pre.replaceWith(card);
            return;
        }

        card.innerHTML = `
            <div class="svg-card-head">
                <span class="svg-card-title">SVG 图形</span>
                <span class="svg-card-meta">独立组件渲染</span>
            </div>
            <div class="svg-stage">${svgMarkup}</div>
        `;
        pre.replaceWith(card);
    });
}

export async function renderRichBlocksIn(container) {
    await renderMermaidIn(container);
    renderSvgIn(container);
}

export function renderMarkdownInto(container, markdownText, wrapperClass = '', copyHandlers) {
    if (!container) {
        return;
    }
    const html = renderMarkdown(markdownText);
    container.innerHTML = wrapperClass ? `<div class="${wrapperClass}">${html}</div>` : html;
    void renderRichBlocksIn(container);
    if (copyHandlers) {
        bindCopyButtons(container, copyHandlers);
    }
}

export function buildLogsBlock(logs, options = {}) {
    if (!logs || !logs.length) {
        return null;
    }

    const { open = false, className = 'message-logs', title = '执行日志' } = options;
    const wrapper = document.createElement('details');
    wrapper.className = className;
    wrapper.open = open;

    const summary = document.createElement('summary');
    summary.className = 'source-toggle';
    summary.innerHTML = `
        <div class="source-toggle-copy">
            <span class="source-toggle-title">${escapeHtml(title)}</span>
            <span class="meta">${logs.length} 条日志</span>
        </div>
        <span class="source-toggle-hint">${open ? '执行中' : '点开查看'}</span>
    `;
    wrapper.appendChild(summary);

    const shell = document.createElement('div');
    shell.className = 'source-list-shell stack';
    logs.forEach((log) => {
        const item = document.createElement('div');
        item.className = 'log-item';
        item.textContent = `[${log.stage}] ${log.message}`;
        shell.appendChild(item);
    });
    wrapper.appendChild(shell);
    return wrapper;
}

function buildSourceItem(result, index) {
    const item = document.createElement('details');
    item.className = 'source-item';

    const titleRow = document.createElement('summary');
    titleRow.className = 'source-item-toggle';
    titleRow.innerHTML = `
        <span class="source-index">${index + 1}</span>
        <span class="source-title">${escapeHtml(result.title || '未命名来源')}</span>
    `;
    item.appendChild(titleRow);

    const body = document.createElement('div');
    body.className = 'source-item-body';
    body.appendChild(buildExpandableText(result.snippet || '暂无摘要', 'source-snippet'));

    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.appendChild(createSafeLink(result.url));
    body.appendChild(meta);
    item.appendChild(body);
    return item;
}

export function buildSourcesBlock(results) {
    const wrapper = document.createElement('details');
    wrapper.className = 'source-block message-sources';

    const summary = document.createElement('summary');
    summary.className = 'source-toggle';
    summary.innerHTML = `
        <div class="source-toggle-copy">
            <span class="source-toggle-title">引用来源</span>
            <span class="meta">${results.length} 条来源</span>
        </div>
        <span class="source-toggle-hint">点开查看</span>
    `;
    wrapper.appendChild(summary);

    const shell = document.createElement('div');
    shell.className = 'source-list-shell';
    const list = document.createElement('div');
    list.className = 'source-list';
    results.forEach((result, index) => {
        list.appendChild(buildSourceItem(result, index));
    });
    shell.appendChild(list);
    wrapper.appendChild(shell);
    return wrapper;
}

export function buildResultLinkRow(result) {
    const row = document.createElement('div');
    row.appendChild(createSafeLink(result.url));
    return row;
}

export function buildSourceMeta(result) {
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.appendChild(createSafeLink(result.url));
    return meta;
}
