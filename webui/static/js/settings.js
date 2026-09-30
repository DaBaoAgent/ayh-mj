/**
 * 设置抽屉（Phase 12 从 app.js 拆出并扩展）。
 *
 * schema 驱动渲染；保存后显示"下一次任务真正会用的运行时值"（RunConfig 快照），
 * 被忽略的字段一律带原因（后端 `ignored`）。
 */
'use strict';

import { $, $$, el, esc, fmtCost } from './ui.js';
import { Pipeline } from './jobs.js';
import { Hermes } from './hermes.js';

const Settings = {
    schema: null,
    values: {},

    async open() {
        $('#settingsDrawer').classList.add('open');
        $('#drawerMask').classList.add('open');
        $('#settingsDrawer').setAttribute('aria-hidden', 'false');
        await this.load();
    },
    close() {
        $('#settingsDrawer').classList.remove('open');
        $('#drawerMask').classList.remove('open');
        $('#settingsDrawer').setAttribute('aria-hidden', 'true');
    },

    async load() {
        try {
            const data = await fetch('/api/settings').then((r) => r.json());
            this.schema = data.schema;
            this.values = data.values || {};
            this.render();
        } catch (e) {
            $('#settingsBody').innerHTML = `<div class="drawer-loading">加载失败: ${esc(e.message)}</div>`;
        }
    },

    render() {
        const body = $('#settingsBody');
        body.innerHTML = '';
        for (const group of (this.schema && this.schema.groups) || []) {
            const g = el('div', 'setting-group');
            g.innerHTML = `<h3>◆ ${esc(group.name)}</h3>`;
            if (group.id === 'pipeline') {
                g.appendChild(el('div', 'pipeline-only-note', '当前唯一链路：热点研究 → 创意策划 → 模板分镜 → 视频生成 → 合成发布'));
            }
            for (const f of group.fields) {
                g.appendChild(this.renderField(f));
            }
            body.appendChild(g);
        }
        // 操作区
        body.appendChild(this.renderActions());
    },

    renderField(f) {
        const row = el('div', 'setting-row');
        const val = this.values[f.key];
        if (f.type === 'toggle') {
            row.innerHTML =
                `<div class="setting-label"><span class="lb">${esc(f.label)}</span>` +
                `<label class="switch ${f.danger ? 'danger' : ''}">` +
                `<input type="checkbox" data-key="${esc(f.key)}" ${val ? 'checked' : ''}>` +
                `<span class="slider"></span></label></div>` +
                `<div class="setting-desc">${esc(f.desc || '')}</div>`;
        } else if (f.type === 'number') {
            row.innerHTML =
                `<div class="setting-label"><span class="lb">${esc(f.label)}</span>` +
                `<div class="number-ctl"><button type="button" data-delta="-1">−</button>` +
                `<input type="number" data-key="${esc(f.key)}" value="${Number(val ?? f.default ?? 0)}" ` +
                `min="${f.min ?? 0}" max="${f.max ?? 99}">` +
                `<button type="button" data-delta="1">＋</button></div></div>` +
                `<div class="setting-desc">${esc(f.desc || '')}</div>`;
            row.querySelectorAll('button[data-delta]').forEach((b) => {
                b.addEventListener('click', () => {
                    const inp = row.querySelector('input');
                    const d = Number(b.dataset.delta);
                    let v = Number(inp.value || 0) + d;
                    v = Math.max(Number(inp.min), Math.min(Number(inp.max), v));
                    inp.value = v;
                });
            });
        } else if (f.type === 'select') {
            const opts = (f.options || []).map((o) =>
                `<option value="${esc(o.value)}" ${val === o.value ? 'selected' : ''}>${esc(o.label)}</option>`).join('');
            row.innerHTML =
                `<div class="setting-label"><span class="lb">${esc(f.label)}</span></div>` +
                `<select class="select-ctl" data-key="${esc(f.key)}">${opts}</select>` +
                `<div class="setting-desc">${esc(f.desc || '')}</div>`;
        } else if (f.type === 'multi') {
            const cur = new Set(Array.isArray(val) ? val : []);
            const chips = (f.options || []).map((o) =>
                `<span class="chip ${cur.has(o.id) ? 'on' : ''}" data-id="${esc(o.id)}" data-region="${esc(o.region || '')}">${esc(o.name)}</span>`).join('');
            row.innerHTML =
                `<div class="setting-label"><span class="lb">${esc(f.label)}</span></div>` +
                `<div class="multi-chips" data-key="${esc(f.key)}">${chips}</div>` +
                `<div class="setting-desc">${esc(f.desc || '')}</div>`;
            row.querySelectorAll('.chip').forEach((c) => {
                c.addEventListener('click', () => c.classList.toggle('on'));
            });
        }
        return row;
    },

    renderActions() {
        const g = el('div', 'setting-group');
        g.innerHTML = '<h3>◆ 操作与维护</h3>';
        const row = el('div', 'action-row');

        const mk = (label, fn) => {
            const b = el('button', 'action-btn', label);
            b.addEventListener('click', fn);
            return b;
        };

        row.appendChild(mk('🔐 检测抖音登录', () => this.actionDouyinCheck()));
        row.appendChild(mk('📱 扫码登录抖音', () => this.actionPost('/api/action/douyin_login', {}, '扫码窗口即将弹出')));
        row.appendChild(mk('📱 扫码登录小红书', () => this.actionPost('/api/action/xiaohongshu_login', {}, '小红书扫码窗口即将弹出')));
        row.appendChild(mk('📱 扫码登录视频号', () => this.actionPost('/api/action/shipinhao_login', {}, '视频号扫码窗口即将弹出')));
        row.appendChild(mk('🧹 清理项目（预览）', () => this.actionCleanup(false)));
        row.appendChild(mk('📂 打开输出目录', () => this.actionPost('/api/action/open_output', {}, '已打开目录')));
        row.appendChild(mk('♻ 重启 Hermes 内核', () => this.actionRestartKernel()));
        row.appendChild(mk('🖥 重启控制台（面板）', () => this.actionPost('/api/restart', {}, '控制台 3 秒后重启')));
        g.appendChild(row);

        const res = el('div', 'action-result');
        res.id = 'actionResult';
        g.appendChild(res);
        return g;
    },

    async actionPost(url, body, okMsg) {
        const res = $('#actionResult');
        res.className = 'action-result show';
        res.textContent = '执行中…';
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const r = await response.json();
            if (!response.ok || r.ok === false) throw new Error(r.detail || r.message || `HTTP ${response.status}`);
            res.textContent = r.message || r.detail || okMsg || JSON.stringify(r);
            res.className = 'action-result show ok';
        } catch (e) {
            res.textContent = `失败: ${e.message}`;
            res.className = 'action-result show fail';
        }
    },

    async actionDouyinCheck() {
        const res = $('#actionResult');
        res.className = 'action-result show';
        res.textContent = '检测中…（启动浏览器约需 10-40 秒）';
        await fetch('/api/action/douyin_check', { method: 'POST' }).catch(() => {});
        const poll = async () => {
            try {
                const st = await fetch('/api/action/state').then((r) => r.json());
                if (st.kind === 'douyin_check') {
                    if (st.status === 'running') {
                        res.textContent = '检测中…';
                        setTimeout(poll, 3000);
                    } else {
                        res.textContent = (st.status === 'ok' ? '✓ ' : '✗ ') + (st.message || '');
                        res.className = `action-result show ${st.status === 'ok' ? 'ok' : 'fail'}`;
                    }
                } else {
                    res.textContent = '检测未启动？';
                }
            } catch { setTimeout(poll, 3000); }
        };
        setTimeout(poll, 3000);
    },

    async actionCleanup(confirm) {
        const res = $('#actionResult');
        res.className = 'action-result show';
        res.textContent = confirm ? '正在清理…' : '正在预览（dry-run）…';
        try {
            const r = await fetch('/api/action/cleanup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirm }),
            }).then((x) => x.json());
            res.textContent = (r.output || '(无输出)') +
                (confirm ? '' : '\n\n── 以上为预览。确认清理请再次点击「清理项目」并确认。');
            res.className = 'action-result show';
            if (!confirm) {
                // 二次确认按钮
                const b = el('button', 'action-btn', '⚠ 确认执行清理');
                b.style.marginTop = '8px';
                b.addEventListener('click', () => this.actionCleanup(true));
                res.appendChild(document.createElement('br'));
                res.appendChild(b);
            }
        } catch (e) {
            res.textContent = `失败: ${e.message}`;
            res.className = 'action-result show fail';
        }
    },

    async actionRestartKernel() {
        const res = $('#actionResult');
        res.className = 'action-result show';
        res.textContent = '正在重启内核（约 20-60 秒）…';
        try {
            const r = await fetch('/api/hermes/restart', { method: 'POST' }).then((x) => x.json());
            res.textContent = (r.ok ? '✓ ' : '✗ ') + (r.detail || '');
            res.className = `action-result show ${r.ok ? 'ok' : 'fail'}`;
        } catch (e) {
            res.textContent = `失败: ${e.message}`;
            res.className = 'action-result show fail';
        }
    },

    collect() {
        const out = {};
        $$('#settingsBody [data-key]').forEach((n) => {
            const key = n.dataset.key;
            if (n.classList && n.classList.contains('multi-chips')) {
                out[key] = Array.from(n.querySelectorAll('.chip.on')).map((c) => c.dataset.id);
            } else if (n.tagName === 'INPUT' && n.type === 'checkbox') {
                out[key] = n.checked;
            } else if (n.tagName === 'INPUT' && n.type === 'number') {
                out[key] = Number(n.value || 0);
            } else if (n.tagName === 'SELECT') {
                out[key] = n.value;
            }
        });
        return out;
    },

    /* 保存后：显示 runtime 生效值 + 被忽略字段的原因（Plan 任务 5） */
    renderRuntime(result) {
        const box = $('#runtimeBox');
        if (!box) return;
        const runtime = result.runtime || {};
        const ignored = result.ignored || {};
        box.innerHTML = '';
        box.appendChild(el('div', 'runtime-title', '运行时生效值'
            + (result.runtime_applies_to ? '（' + result.runtime_applies_to + '）' : '')));
        const table = el('div', 'runtime-grid');
        for (const [key, value] of Object.entries(runtime)) {
            const cell = el('div', 'runtime-cell');
            cell.appendChild(el('span', 'rk', key));
            cell.appendChild(el('span', 'rv', Array.isArray(value) ? value.join('、') : String(value)));
            table.appendChild(cell);
        }
        box.appendChild(table);
        box.appendChild(el('div', 'runtime-saved',
            '已保存：' + (Object.keys(result.saved || {}).join('、') || '（无变化）')));
        const ignoredKeys = Object.keys(ignored);
        if (ignoredKeys.length) {
            const list = el('div', 'runtime-ignored');
            list.appendChild(el('div', 'runtime-title', '被忽略的字段'));
            for (const key of ignoredKeys) {
                list.appendChild(el('div', 'runtime-ignored-row', key + '：' + ignored[key]));
            }
            box.appendChild(list);
        }
        box.classList.add('show');
    },

    async save() {
        const hint = $('#saveHint');
        try {
            const r = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.collect()),
            }).then((x) => x.json());
            const ignored = Object.keys(r.ignored || {});
            hint.textContent = ignored.length ? `已保存（${ignored.length} 项被忽略）` : '✓ 已保存';
            hint.className = 'save-hint show' + (ignored.length ? ' err' : '');
            setTimeout(() => hint.classList.remove('show'), 2600);
            this.renderRuntime(r);
            Pipeline.refresh();
        } catch (e) {
            hint.textContent = `保存失败: ${e.message}`;
            hint.className = 'save-hint show err';
        }
    },
};

export { Settings };
