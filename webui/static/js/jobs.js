/**
 * 生产流水线面板 + 任务台（Phase 12 从 app.js 拆出）。
 *
 *  · Pipeline：SSE + 轮询刷新，阶段状态只读 canonical 事实；
 *  · Jobs：真实任务列表 / 详情 / 取消 / 重试 / 恢复。
 */
'use strict';

import {
    $, $$, el, esc, fmtTime, fmtBytes, fmtCost, stageLabel, stateLabel, stateTone,
    CANONICAL_STAGES, CANONICAL_SIDE,
} from './ui.js';
import { listJobs, jobDetail, jobAction } from './api.js';
import { Store } from './store.js';

/* ================================================================
 * 二、流水线状态（SSE + 轮询）
 * ================================================================ */
const Pipeline = {
    stages: ['trend', 'copy', 'storyboard', 'generate', 'compose', 'publish'],
    stageNames: {},
    running: false,
    eventSource: null,

    async refresh() {
        try {
            const res = await fetch('/api/state');
            if (!res.ok) throw new Error(`状态读取失败 (${res.status})`);
            const data = await res.json();
            this.apply(data);
        } catch (e) { /* 网络抖动，跳过 */ }
    },

    apply(data) {
        const run = data.run || {};
        this.running = !!run.running;

        // 状态胶囊
        const pill = $('#statusPill');
        pill.classList.toggle('running', this.running);
        // canonical 计数：状态的唯一判据（不再对 run.message 做字符串包含/相等判断）
        const counts = run.jobs_by_status || {};
        const needHuman = Number(counts.BLOCKED || 0) + Number(counts.FAILED || 0);
        $('#statusText').textContent = this.running
            ? `运行中 · ${this.stageName(run.current_stage) || ''}`
            : (needHuman ? `待命 · ${needHuman} 条需人工` : '待命');

        // 开始/停止按钮
        $('#btnStart').disabled = this.running;
        $('#btnStop').disabled = !this.running;

        // 进度环
        const prog = Number(run.progress || 0);
        const circ = 2 * Math.PI * 45;
        const ring = $('#ringProgress');
        if (ring) ring.style.strokeDashoffset = circ * (1 - prog / 100);
        $('#ringPercent').textContent = Math.round(prog);
        $('#renderPercent').textContent = `${Math.round(prog)}%`;
        const everRan = Number(run.total || 0) > 0;
        $('#renderState').textContent = this.running
            ? (this.stageName(run.current_stage) || '正在启动')
            : (needHuman ? '存在需人工任务' : (everRan ? '上一任务完成' : '等待任务'));

        // 阶段状态：只用 canonical 事实（run.stage 是 JobStore 的状态，run.current_stage
        // 是后端 FRONTEND_STAGE 映射，jobs_by_status 是状态计数）—— 不做字符串包含判断。
        const canonIdx = run.stage ? CANONICAL_STAGES.indexOf(run.stage) : -1;
        const curIdx = canonIdx >= 0 ? canonIdx : this.stages.indexOf(run.current_stage);
        const blocked = needHuman > 0;
        const finished = !this.running && prog >= 100;
        $$('.stage').forEach((elm, idx) => {
            let st = 'idle', mark = '·';
            if (this.running && curIdx >= 0) {
                if (idx < curIdx) { st = 'done'; mark = '✓'; }
                else if (idx === curIdx) { st = 'active'; mark = '▶'; }
            } else if (finished && !blocked) {
                st = 'done'; mark = '✓';
            } else if (blocked && idx === Math.max(curIdx, 0)) {
                st = 'error'; mark = '✗';
            }
            elm.dataset.state = st;
            elm.querySelector('.stage-state').textContent = mark;
        });

        // 真实状态机条：13 个 canonical 主线态 + 旁路态计数
        this.renderStateStrip(run);

        $('#currentStage').textContent = this.running
            ? (this.stageName(run.current_stage) || '—') : '—';
        $('#runMessage').textContent = run.message || '待命';
        $('#engRun').textContent = this.running ? '运行中' : '待命';

        // 统计（仅在有数据时更新，防 SSE 轻量帧覆盖）
        if (data.stats) {
            const stats = data.stats;
            $('#statTrends').textContent = stats.trends_total ?? 0;
            $('#statJobs').textContent = stats.jobs_total ?? 0;
            $('#statReady').textContent = stats.jobs_ready ?? 0;
            $('#statPublished').textContent = stats.jobs_published ?? 0;
            $('#topToday').textContent = stats.published_today ?? 0;
            $('#topJobs').textContent = stats.jobs_total ?? 0;
            $('#topReady').textContent = stats.jobs_ready ?? 0;
            $('#engToday').textContent = stats.published_today ?? 0;
            $('#engTrends').textContent = stats.trends_total ?? 0;
        }
        if (data.console) window.__consoleState = data.console;
        if (data.hermes) {
            const h = data.hermes;
            $('#engKernel').textContent = h.ready ? `在线 :${h.port}` : '离线';
            $('#topKernel').textContent = h.ready ? '就绪' : '离线';
        }
        if (data.resources) {
            const resources = data.resources;
            const fields = [
                ['gpu', 'Gpu'], ['cpu', 'Cpu'], ['memory', 'Memory'], ['disk', 'Disk'],
            ];
            for (const [key, label] of fields) {
                const value = resources[key];
                $(`#eng${label}`).textContent = value == null ? '--' : `${Math.round(value)}%`;
                $(`#ring${label}`).style.setProperty('--value', value == null ? 0 : Math.max(0, Math.min(100, value)));
            }
            $('#topGpu').textContent = resources.gpu == null ? '--' : `${Math.round(resources.gpu)}%`;
            $('#topStorage').textContent = resources.disk_free_gb == null ? '--' : `${resources.disk_free_gb} GB`;
        }
    },

    stageName(id) {
        const map = { trend: '热点雷达', copy: '创意策划', storyboard: '分镜策划',
                      generate: '视频生成', compose: '后期合成', publish: '发布互动' };
        return map[id] || '';
    },

    renderStateStrip(run) {
        const strip = $('#stateStrip');
        if (!strip) return;
        const current = String(run.stage || '').toUpperCase();
        const counts = run.jobs_by_status || {};
        strip.innerHTML = '';
        for (const state of CANONICAL_STAGES) {
            const chip = el('span', 'state-chip', stateLabel(state));
            chip.dataset.state = state;
            if (state === current) chip.classList.add('on');
            strip.appendChild(chip);
        }
        for (const side of CANONICAL_SIDE) {
            const n = Number(counts[side] || 0);
            if (!n) continue;
            const chip = el('span', 'state-chip side', `${stateLabel(side)} ${n}`);
            chip.dataset.state = side;
            chip.dataset.tone = 'side';
            strip.appendChild(chip);
        }
    },

    startSSE() {
        if (this.eventSource) this.eventSource.close();
        const es = new EventSource('/api/logs');
        this.eventSource = es;
        es.onmessage = (ev) => {
            try {
                const data = JSON.parse(ev.data);
                if (data.type === 'status') {
                    // 轻量帧：只更新 run 字段（stats/hermes/console 等由 4s 轮询负责）
                    const wasRunning = this.running;
                    this.apply({ run: data.data });
                    if (data.data && data.data.running !== undefined && data.data.running !== wasRunning) {
                        this.refresh();
                    }
                } else if (data.type === 'log') {
                    this.addLog(data.level || 'info', data.message || '');
                }
            } catch { /* 非 JSON 行 */ }
        };
        es.onerror = () => {
            es.close();
            if (this.eventSource === es) {
                this.eventSource = null;
                setTimeout(() => this.startSSE(), 5000);
            }
        };
    },

    addLog(level, message) {
        const box = $('#logsBox');
        const line = el('div', `log-line ${level}`);
        line.innerHTML = `<span class="log-t">${fmtTime()}</span>${esc(message)}`;
        box.appendChild(line);
        while (box.children.length > 260) box.removeChild(box.firstChild);
        box.scrollTop = box.scrollHeight;
    },
};


/* ================================================================
 * 二·B、任务台（Phase 12）：canonical 任务列表 + 任务详情
 *   全部字段来自 /api/jobs 与 /api/jobs/{uid}；前端只渲染，不推断。
 * ================================================================ */
const Jobs = {
    async load(params) {
        const next = params || {};
        const filter = next.filter !== undefined ? next.filter : Store.get().filter;
        try {
            const data = await listJobs({ status: filter || undefined, limit: 30 });
            Store.set({ jobs: data.jobs || [], jobsTotal: data.total || null, filter });
            this.render();
        } catch (e) {
            const box = $('#jobsList');
            if (box) box.innerHTML = '<div class="empty-hint">任务列表读取失败：' + esc(e.message) + '</div>';
        }
    },

    render() {
        const box = $('#jobsList');
        if (!box) return;
        const st = Store.get();
        const badge = $('#jobsCount');
        if (badge) badge.textContent = `${st.jobs.length} / ${(st.jobsTotal || {}).total || 0}`;
        box.innerHTML = '';
        if (!st.jobs.length) {
            box.appendChild(el('div', 'empty-hint', '暂无任务'));
            return;
        }
        for (const job of st.jobs) box.appendChild(this.row(job));
    },

    row(job, blocked) {
        const item = el('button', 'job-row');
        item.type = 'button';
        item.dataset.uid = job.uid;                  // 可定位/可断言（也方便前端调试）
        item.dataset.status = job.status;
        item.dataset.tone = stateTone(job.status);
        if (job.uid === Store.get().selectedUid) item.classList.add('selected');
        const top = el('div', 'job-row-top');
        top.appendChild(el('span', 'job-state', stateLabel(job.status)));
        top.appendChild(el('span', 'job-uid', job.uid));
        item.appendChild(top);
        item.appendChild(el('div', 'job-goal', job.goal || '（无目标描述）'));
        const tail = el('div', 'job-row-tail');
        tail.appendChild(el('span', 'job-stage', stageLabel(job.stage)));
        tail.appendChild(el('span', 'job-cost', fmtCost(job.cost_spent)));
        if (job.actions && job.actions.retry) tail.appendChild(el('span', 'job-flag', '需人工'));
        if (blocked && blocked.code) tail.appendChild(el('span', 'job-flag', blocked.code));
        item.appendChild(tail);
        item.addEventListener('click', () => this.open(job.uid));
        return item;
    },

    async open(uid) {
        Store.set({ selectedUid: uid });
        const drawer = $('#jobDrawer');
        const mask = $('#jobMask');
        if (drawer) { drawer.classList.add('open'); drawer.setAttribute('aria-hidden', 'false'); }
        if (mask) mask.classList.add('open');
        const body = $('#jobDrawerBody');
        if (body) body.innerHTML = '<div class="drawer-loading">加载任务详情…</div>';
        try {
            const detail = await jobDetail(uid);
            Store.set({ detail: detail });
            this.renderDetail(detail);
            this.render();
        } catch (e) {
            if (body) body.innerHTML = '<div class="drawer-loading">读取失败：' + esc(e.message) + '</div>';
        }
    },

    close() {
        const drawer = $('#jobDrawer');
        const mask = $('#jobMask');
        if (drawer) { drawer.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true'); }
        if (mask) mask.classList.remove('open');
    },

    async reload() {
        await this.load();
        const uid = Store.get().selectedUid;
        if (uid) await this.open(uid);
    },

    async act(action, confirmText) {
        const uid = Store.get().selectedUid;
        if (!uid) return;
        if (confirmText && !window.confirm(confirmText)) return;
        const msg = $('#jobActionMsg');
        if (msg) { msg.className = 'action-result show'; msg.textContent = '执行中…'; }
        try {
            const r = await jobAction(uid, action);
            if (msg) {
                msg.className = 'action-result show ok';
                msg.textContent = r.message || (action + ' 已提交');
            }
        } catch (e) {
            if (msg) {
                msg.className = 'action-result show fail';
                msg.textContent = '失败：' + e.message;
            }
        }
        await this.load();
        await this.open(uid);
    },

    /* ---------- 任务详情渲染 ---------- */
    section(title) {
        const sec = el('div', 'job-section');
        sec.appendChild(el('h4', null, title));
        return sec;
    },

    kv(sec, label, value) {
        const row = el('div', 'job-kv');
        row.appendChild(el('span', 'k', label));
        row.appendChild(el('span', 'v', value == null || value === '' ? '—' : String(value)));
        sec.appendChild(row);
        return row;
    },

    renderDetail(detail) {
        const body = $('#jobDrawerBody');
        if (!body) return;
        const job = detail.job || {};
        const summary = detail.summary || {};
        const title = $('#jobDrawerTitle');
        if (title) title.textContent = `${job.uid || ''} · ${stateLabel(job.status)}`;
        body.innerHTML = '';

        if (detail.blocked) {
            const box = el('div', 'job-blocked');
            box.appendChild(el('div', 'job-blocked-head',
                '需要人工：' + (detail.blocked.code || '未知错误')));
            box.appendChild(el('div', 'job-blocked-msg', detail.blocked.message || ''));
            box.appendChild(el('div', 'job-blocked-action', detail.blocked.human_action || ''));
            if (detail.blocked.next_action) {
                box.appendChild(el('div', 'job-blocked-hint', '系统建议动作：' + detail.blocked.next_action));
            }
            body.appendChild(box);
        }

        const head = this.section('任务');
        this.kv(head, '状态', stateLabel(job.status));
        this.kv(head, '当前阶段', stageLabel(job.current_stage));
        this.kv(head, '目标', job.goal);
        this.kv(head, 'dry 演练',
            summary.dry === true ? '是' : (summary.dry === false ? '否' : '—'));
        this.kv(head, '成本', fmtCost(job.cost_spent) + ' / 上限 ' + fmtCost(job.budget_cap));
        this.kv(head, '创建', job.created_at);
        this.kv(head, '更新', job.updated_at);
        this.kv(head, '错误码', job.error_code);
        body.appendChild(head);

        const creative = detail.creative;
        const csec = this.section('CreativeDNA');
        if (creative) {
            const dna = creative.dna || {};
            this.kv(csec, '片型 genre', dna.genre);
            this.kv(csec, '钩子 hook_type', dna.hook_type);
            this.kv(csec, '镜头结构 shot_pattern', dna.shot_pattern);
            this.kv(csec, '角度 angle', dna.angle);
            this.kv(csec, '卖点 sales_point', dna.sales_point);
            this.kv(csec, '风险标记', (dna.risk_flags || []).join('、'));
            this.kv(csec, '骨架', creative.structure_name || creative.structure);
            this.kv(csec, '规划日', creative.day);
        } else {
            csec.appendChild(el('div', 'job-empty', '该任务没有 CreativeDNA 落盘（未走创意规划阶段）。'));
        }
        body.appendChild(csec);

        const qsec = this.section('质检与评分');
        const qa = detail.qa || {};
        if (qa.count) {
            this.kv(qsec, '质检次数', qa.count);
            this.kv(qsec, '最近一次', (qa.latest_kind || '—') + ' / ' + (qa.latest_score == null ? '—' : qa.latest_score)
                + (qa.latest_passed === null ? '' : (qa.latest_passed ? '（通过）' : '（未通过）')));
            this.kv(qsec, '最低分', qa.min_score);
        } else {
            qsec.appendChild(el('div', 'job-empty', '暂无质检记录。'));
        }
        for (const ev of (detail.evaluations || []).slice(-6)) {
            this.kv(qsec, ev.kind, ev.score == null ? '—' : ev.score);
        }
        body.appendChild(qsec);

        const asec = this.section(`尝试与供应商（${(detail.attempts || []).length} 次尝试）`);
        for (const att of (detail.attempts || []).slice(-8)) {
            this.kv(asec, att.stage || '—',
                `${att.status || '—'}${att.error_code ? ' · ' + att.error_code : ''}`
                + (att.attempt_no ? ` · #${att.attempt_no}` : ''));
        }
        for (const task of (detail.provider_tasks || [])) {
            this.kv(asec, 'provider ' + (task.stage || ''),
                `${task.status || '—'} · ${task.workflow || '—'} · ${task.task_id || '—'}`);
        }
        if (!(detail.attempts || []).length && !(detail.provider_tasks || []).length) {
            asec.appendChild(el('div', 'job-empty', '暂无尝试记录。'));
        }
        body.appendChild(asec);

        const rsec = this.section('修复历史');
        const rsum = detail.repair_summary || {};
        this.kv(rsec, '修复次数', rsum.count == null ? '—' : rsum.count);
        this.kv(rsec, '修复成本', fmtCost(rsum.cost));
        for (const rep of (detail.repairs || []).slice(-8)) {
            this.kv(rsec, rep.error_code || '—',
                `${rep.action || '—'} · ${rep.status || '—'} · ${fmtCost(rep.cost)}`);
        }
        body.appendChild(rsec);

        const art = this.section(`产物（${(detail.artifacts || []).length}）`);
        for (const a of (detail.artifacts || [])) {
            this.kv(art, a.type, (a.name || '—') + (a.exists ? '' : '（文件缺失）'));
        }
        if (!(detail.artifacts || []).length) art.appendChild(el('div', 'job-empty', '暂无产物。'));
        body.appendChild(art);

        const psec = this.section('发布状态');
        for (const p of (detail.publishes || [])) {
            this.kv(psec, p.platform, `${p.status || '—'}${p.post_id ? ' · ' + p.post_id : ''}`);
        }
        if (!(detail.publishes || []).length) psec.appendChild(el('div', 'job-empty', '尚未发布。'));
        body.appendChild(psec);

        const msec = this.section('表现数据');
        for (const m of (detail.performance || []).slice(-4)) {
            this.kv(msec, m.platform + ' ' + (m.snapshot_time || ''),
                (m.metric_count == null ? '—' : m.metric_count) + ' 个指标');
        }
        if (!(detail.performance || []).length) msec.appendChild(el('div', 'job-empty', '还没有表现快照。'));
        body.appendChild(msec);

        const act = el('div', 'job-actions');
        const mk = (label, action, fn, disabled) => {
            const b = el('button', 'action-btn', label);
            b.dataset.action = action;
            if (disabled) b.disabled = true;
            else b.addEventListener('click', fn);
            return b;
        };
        const actions = summary.actions || {};
        act.appendChild(mk('取消任务', 'cancel', () => this.act('cancel', '确认取消该任务？'),
            !(actions.cancel || summary.actions == null) ));
        act.appendChild(mk('重试', 'retry', () => this.act('retry'), !actions.retry));
        act.appendChild(mk('恢复', 'resume', () => this.act('resume'), !actions.resume));
        body.appendChild(act);
        const msg = el('div', 'action-result');
        msg.id = 'jobActionMsg';
        body.appendChild(msg);
    },
};

export { Pipeline, Jobs };
