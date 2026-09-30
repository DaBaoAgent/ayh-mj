/**
 * 成片区（Phase 12 从 app.js 拆出并扩展）。
 *
 *  · 视频卡：/api/outputs（最终成片 + 缩略图）；
 *  · 物料行：/api/materials —— 视频 + QA 摘要 + 标题/封面方案 + 发布状态 + 表现数据。
 */
'use strict';

import { $, el, esc, fmtTime, fmtBytes, fmtPct, stageLabel, stateLabel, stateTone } from './ui.js';
import { materials } from './api.js';
import { Store } from './store.js';

const Outputs = {
    async load() {
        await Promise.all([this.loadVideos(), this.loadMaterials()]);
    },

    async loadVideos() {
        try {
            const outputs = await fetch('/api/outputs?limit=3').then((r) => r.json());
            Store.set({ outputs: outputs });
            const grid = $('#outputsGrid');
            if (!grid) return;
            if (!outputs.length) {
                grid.innerHTML = '<div class="empty-hint">暂无成片</div>';
                return;
            }
            grid.innerHTML = '';
            for (const o of outputs) {
                const item = el('a', 'output-item');
                item.href = o.video;
                item.target = '_blank';
                item.rel = 'noopener noreferrer';
                item.title = `${o.name} · 新窗口播放`;
                if (o.thumb) {
                    const img = el('img');
                    img.src = `${o.thumb}?v=${encodeURIComponent(o.mtime || '')}`;
                    img.alt = `${o.name} 缩略图`;
                    img.loading = 'lazy';
                    item.appendChild(img);
                } else {
                    item.appendChild(el('span', 'output-placeholder'));
                }
                const meta = el('div', 'output-meta');
                meta.appendChild(el('div', 'output-name', o.name));
                meta.appendChild(el('div', 'output-sub',
                    `${fmtBytes(o.size)} · ${String(o.mtime).slice(5, 16).replace('T', ' ')}`));
                item.appendChild(meta);
                grid.appendChild(item);
            }
        } catch (e) { /* 网络抖动：保留上一次渲染 */ }
    },

    async loadMaterials() {
        const box = $('#materialsList');
        if (!box) return;
        try {
            const data = await materials(8);
            const items = data.materials || [];
            Store.set({ materials: items });
            box.innerHTML = '';
            if (!items.length) {
                box.appendChild(el('div', 'empty-hint', '还没有可展示的成片物料'));
                return;
            }
            for (const m of items) box.appendChild(this.card(m));
        } catch (e) {
            box.innerHTML = '<div class="empty-hint">物料读取失败：' + esc(e.message) + '</div>';
        }
    },

    card(m) {
        const card = el('div', 'material-card');
        card.dataset.uid = m.uid;
        card.dataset.status = m.status;
        card.dataset.tone = stateTone(m.status);
        const head = el('div', 'material-head');
        head.appendChild(el('span', 'material-state', stateLabel(m.status)));
        head.appendChild(el('span', 'material-video', m.video ? (m.video.split(/[\\/]/).pop()) : '（无成片文件）'));
        card.appendChild(head);

        if (m.title) {
            const t = el('div', 'material-title');
            t.textContent = '标题方案：' + m.title;
            card.appendChild(t);
        }
        if (m.cover) {
            const c = el('div', 'material-cover');
            c.textContent = '封面文案：' + m.cover;
            card.appendChild(c);
        }
        const qa = m.qa || {};
        if (qa.count) {
            card.appendChild(el('div', 'material-qa',
                `QA：${qa.count} 次，最近 ${qa.latest_score == null ? '—' : qa.latest_score}`
                + (qa.min_score == null ? '' : `，最低 ${qa.min_score}`)));
        }
        const pub = m.publish || [];
        card.appendChild(el('div', 'material-publish', pub.length
            ? ('发布：' + pub.map((p) => `${p.platform}/${p.status}`).join('、'))
            : '发布：未发布'));
        const perf = m.performance;
        if (perf) {
            const metrics = perf.metrics || {};
            card.appendChild(el('div', 'material-perf',
                `表现：${perf.platform || '—'} · ${perf.metric_count == null ? '—' : perf.metric_count} 个指标`
                + (metrics.completion == null ? '' : ` · 完播 ${fmtPct(metrics.completion)}`)));
        } else {
            card.appendChild(el('div', 'material-perf', '表现：暂无快照'));
        }
        if (m.blocked) {
            card.appendChild(el('div', 'material-blocked',
                '需人工：' + (m.blocked.human_action || m.blocked.code || '')));
        }
        const actions = el('div', 'material-actions');
        if (m.video_url) {
            const a = el('a', 'material-link', '播放成片');
            a.href = m.video_url;
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
            actions.appendChild(a);
        }
        const detailBtn = el('button', 'action-btn small', '查看任务详情');
        detailBtn.addEventListener('click', async () => {
            const mod = await import('./jobs.js');
            mod.Jobs.open(m.uid);
        });
        actions.appendChild(detailBtn);
        card.appendChild(actions);
        return card;
    },
};

export { Outputs };
