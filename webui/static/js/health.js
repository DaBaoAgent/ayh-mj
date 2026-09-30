/**
 * System Health 面板（Phase 12）。
 *
 * 每个能力直接显示后端 tools.health_check 给的 READY / DEGRADED / BLOCKED，
 * 缺什么、怎么补（fix）都来自后端，前端不做二次判定。
 */
'use strict';

import { $, el, esc } from './ui.js';
import { systemHealth } from './api.js';
import { Store } from './store.js';

const TONE_TEXT = { READY: '就绪', DEGRADED: '降级', BLOCKED: '阻塞', UNKNOWN: '未知' };

const Health = {
    load() {
        return systemHealth().then((report) => {
            Store.set({ health: report });
            this.render(report);
            return report;
        }).catch((e) => {
            this.render({ status: 'UNKNOWN', error: String(e.message || e), capabilities: [] });
        });
    },

    render(report) {
        const grid = $('#healthGrid');
        if (!grid) return;
        const badge = $('#healthStatus');
        const data = report || {};
        if (badge) {
            badge.textContent = TONE_TEXT[data.status] || data.status || '未知';
            badge.dataset.tone = String(data.status || 'UNKNOWN').toLowerCase();
        }
        grid.innerHTML = '';
        const caps = data.capabilities || [];
        if (!caps.length) {
            grid.appendChild(el('div', 'empty-hint', data.error ? ('体检失败：' + data.error) : '暂无能力数据'));
            return;
        }
        for (const cap of caps) {
            const row = el('div', 'health-row');
            row.dataset.tone = String(cap.status || 'UNKNOWN').toLowerCase();
            const head = el('div', 'health-head');
            head.innerHTML = '<b>' + esc(cap.name) + '</b>'
                + '<span class="health-chip">' + esc(TONE_TEXT[cap.status] || cap.status || '—') + '</span>'
                + (cap.required ? '<span class="health-req">必需</span>' : '');
            row.appendChild(head);
            row.appendChild(el('div', 'health-detail', cap.detail || ''));
            if (cap.status !== 'READY' && cap.fix) {
                row.appendChild(el('div', 'health-fix', '修复：' + cap.fix));
            }
            grid.appendChild(row);
        }
    },
};

export { Health };
