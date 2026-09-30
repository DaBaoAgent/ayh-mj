/**
 * Hermes 控制台（Phase 12 从 app.js 拆出）。
 *
 * 只负责"对话/思考/工具进度"的呈现，**不再是另一套任务真相**：
 * 任务状态一律来自 JobStore（Pipeline / Jobs 面板），这里最多把工具事件转成日志。
 */
'use strict';

import { $, $$, el, esc, fmtTime, fmtBytes, NeuralStage } from './ui.js';
import { Pipeline } from './jobs.js';

/* ================================================================
 * 一、Hermes 控制台（核心）
 * ================================================================ */
const Hermes = {
    ws: null,
    connState: 'off',          // off | connecting | on
    sid: null,                  // 当前 live 会话 id
    busy: false,
    ready: false,               // 会话初始化完成
    turn: null,                 // 当前回合 DOM
    toolCards: new Map(),       // tool_id -> {card, body}
    toolsByName: new Map(),     // 兜底：name -> 最近一张卡（tool_id 缺失时）
    reconnectMs: 1000,
    root: '.',                  // 会话 cwd，由 app.js 注入服务端下发的项目根
    reconnectTimer: null,
    turnTimer: null,
    turnStartedAt: 0,
    pendingInteractive: null,   // 当前交互请求（approval/clarify）

    setRoot(root) {
        this.root = root || '.';
        return this;
    },

    /* ---------- 连接管理 ---------- */
    connect() {
        this.setConn('connecting');
        let ws;
        try {
            const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
            ws = new WebSocket(`${scheme}://${location.host}/ws/hermes`);
        } catch (e) {
            this.scheduleReconnect();
            return;
        }
        this.ws = ws;
        ws.onopen = () => {
            this.reconnectMs = 1000;
            this.setConn('on');
        };
        ws.onmessage = (ev) => {
            let obj;
            try { obj = JSON.parse(ev.data); } catch { return; }
            this.onFrame(obj);
        };
        ws.onclose = () => {
            // A stale socket can close after a new one has connected.
            if (this.ws !== ws) return;
            this.setConn('off');
            this.ready = false;
            this.sid = null;
            this.stopTurnTimer();
            this.setLiveStatus('连接断开 · 正在重连…', false);
            NeuralStage.set('error', '核心链路正在重连');
            this.scheduleReconnect();
        };
        ws.onerror = () => { /* onclose 会跟进 */ };
    },

    scheduleReconnect() {
        if (this.reconnectTimer) return;
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, this.reconnectMs);
        this.reconnectMs = Math.min(this.reconnectMs * 1.8, 15000);
    },

    setConn(st) {
        this.connState = st;
        const badge = $('#connBadge');
        const dot = $('#holoDot');
        const map = { on: ['在线', 'on'], connecting: ['连接中…', 'connecting'], off: ['离线', 'off'] };
        const [text, cls] = map[st] || map.off;
        badge.textContent = text;
        badge.dataset.state = cls;
        dot.classList.toggle('on', st === 'on');
        $('#btnSend').disabled = st !== 'on' || !this.ready;
    },

    /* ---------- RPC ---------- */
    rpcSeq: 0,
    rpcPending: new Map(),

    rpc(method, params = {}, timeoutMs = 120000) {
        return new Promise((resolve, reject) => {
            if (!this.ws || this.ws.readyState !== 1) {
                reject(new Error('未连接内核'));
                return;
            }
            const id = 'w' + (++this.rpcSeq);
            this.rpcPending.set(id, { resolve, reject });
            this.ws.send(JSON.stringify({ id, method, params }));
            setTimeout(() => {
                if (this.rpcPending.has(id)) {
                    this.rpcPending.delete(id);
                    reject(new Error(`RPC 超时: ${method}`));
                }
            }, timeoutMs);
        });
    },

    onFrame(obj) {
        // RPC 响应
        if (obj.id && this.rpcPending.has(obj.id)) {
            const { resolve, reject } = this.rpcPending.get(obj.id);
            this.rpcPending.delete(obj.id);
            if (obj.error) reject(new Error(obj.error.message || JSON.stringify(obj.error)));
            else resolve(obj.result || {});
            return;
        }
        // 事件
        if (obj.method === 'event' && obj.params) {
            const { type, payload, session_id } = obj.params;
            try { this.onEvent(type, payload || {}, session_id || ''); }
            catch (e) { console.error('事件处理异常', type, e); }
        }
    },

    /* ---------- 会话初始化 ---------- */
    async initSession() {
        this.setLiveStatus('初始化内核会话…', false);
        let resumed = null;
        const stored = localStorage.getItem('console_session_id');
        if (stored) {
            try {
                const r = await this.rpc('session.resume', { session_id: stored, lazy: true });
                if (r && r.session_id) resumed = r;
            } catch { /* fallthrough */ }
        }
        if (!resumed) {
            try {
                const r = await this.rpc('session.resume', { session_id: '轻便侠控制台', lazy: true });
                if (r && r.session_id) resumed = r;
            } catch { /* fallthrough */ }
        }
        if (resumed) {
            this.sid = resumed.session_id;
            if (resumed.stored_session_id) localStorage.setItem('console_session_id', resumed.stored_session_id);
            this.ready = true;
            this.setConn('on');
            if (resumed.info && resumed.info.model) {
                $('#modelBadge').textContent = `${resumed.info.model} · ${resumed.info.provider || ''}`.trim();
            }
            if (Array.isArray(resumed.messages) && resumed.messages.length) {
                this.renderHistory(resumed.messages);
            }
            this.setLiveStatus('会话已恢复 · standby', false);
            return;
        }
        // 新建
        try {
            const r = await this.rpc('session.create', {
                title: '轻便侠控制台',
                cwd: this.root || '.',
            });
            this.sid = r.session_id;
            if (r.stored_session_id) localStorage.setItem('console_session_id', r.stored_session_id);
            this.ready = true;
            this.setConn('on');
            if (r.info && r.info.model) {
                $('#modelBadge').textContent = `${r.info.model} · ${r.info.provider || ''}`.trim();
            }
            this.setLiveStatus('新会话就绪 · standby', false);
        } catch (e) {
            this.setLiveStatus(`会话初始化失败: ${e.message}`, false);
            setTimeout(() => this.initSession(), 5000);
        }
    },

    async newChat() {
        try {
            const r = await this.rpc('session.create', { cwd: this.root || '.' });
            this.sid = r.session_id;
            if (r.stored_session_id) localStorage.setItem('console_session_id', r.stored_session_id);
            this.clearView(false);
            this.addSystem('◢ 已开启全新会话 —— 这是一条独立对话线（刷新页面可通过"历史"回来）');
        } catch (e) {
            this.addSystem(`新对话失败: ${e.message}`);
        }
    },

    /* ---------- 事件处理（对齐桌面版语义） ---------- */
    onEvent(type, p, sid) {
        // 归属检查：忽略其他会话的事件（例如后台 cron 会话）
        if (sid && this.sid && sid !== this.sid) return;

        switch (type) {
            case 'gateway.ready':
                if (!this.ready) this.initSession();
                break;

            case 'session.info':
                if (p.model) {
                    $('#modelBadge').textContent = `${p.model} · ${p.provider || ''}`.trim();
                    $('#topKernel').textContent = '就绪';
                }
                break;

            case 'session.title':
                if (p.title) $('#modelBadge').title = p.title;
                break;

            case 'message.start':
                this.beginTurn(true);
                break;

            case 'thinking.delta':
                if (p.text) {
                    this.setLiveStatus(p.text, true, true);
                    NeuralStage.set('thinking');
                }
                break;

            case 'reasoning.delta':
                if (p.text) {
                    this.ensureTurn();
                    this.streamPush('think', p.text);
                    this.setLiveStatus('思考中…', true);
                    NeuralStage.set('thinking');
                }
                break;

            case 'reasoning.available':
                if (p.text) {
                    this.ensureTurn();
                    // 整块思考文本：替换（final）
                    if (this.turn && this.turn.thinkBody) {
                        this.streamFlush();
                        this.turn.thinkBody.textContent = p.text;
                        this.scrollThink();
                    }
                }
                break;

            case 'message.delta':
                if (p.text) {
                    this.ensureTurn();
                    this.streamPush('bubble', p.text);
                    this.setLiveStatus('输出回复中…', true);
                }
                break;

            case 'message.interim':
                // 工具间插话 → 封存当前 bubble
                if (p.text) {
                    this.ensureTurn();
                    this.streamFlush();
                    if (this.turn.bubble && this.turn.bubble.textContent.trim()) {
                        this.turn.bubble.classList.remove('streaming');
                        const fresh = el('div', 'msg-bubble streaming');
                        this.turn.group.appendChild(fresh);
                        this.turn.bubble = fresh;
                    }
                    this.streamPush('bubble', p.text);
                }
                break;

            case 'message.complete':
                this.endTurn(p);
                break;

            case 'tool.generating':
                if (p.name) this.setLiveStatus(`正在生成工具调用：${p.name}`, true);
                break;

            case 'tool.start':
            case 'tool.progress':
                this.upsertTool(p, type === 'tool.start' ? 'running' : 'running');
                this.setLiveStatus(`工具执行中：${p.name || ''}`, true);
                NeuralStage.set('tool', p.name ? `正在调度：${p.name}` : undefined);
                if (type === 'tool.start') Pipeline.addLog('info', `Hermes 调用工具：${p.name || 'tool'}`);
                break;

            case 'tool.complete':
                this.upsertTool(p, p.error ? 'failed' : 'done');
                Pipeline.addLog(p.error ? 'error' : 'success', `工具${p.error ? '失败' : '完成'}：${p.name || 'tool'}`);
                break;

            case 'todo.updated':
                /* 任务清单事件：暂不单独渲染 */
                break;

            case 'approval.request':
                this.showApproval(p);
                break;

            case 'clarify.request':
                this.showClarify(p);
                break;

            case 'error':
                this.showError(p);
                this.endTurn({ status: 'error', ...p });
                break;

            case 'status.update':
                if (p.text || p.message) this.setLiveStatus(p.text || p.message, false);
                break;

            case 'bridge.error':
                this.addSystem(`⚠ 内核桥接失败：${p.message || ''}`);
                this.setLiveStatus('内核不可用 · 稍后自动重试', false);
                Pipeline.addLog('error', `Hermes 桥接失败：${p.message || ''}`);
                break;

            case 'reaction':
            case 'sessions.changed':
            case 'session.compacted':
                break;

            default:
                break;
        }
    },

    /* ---------- 回合 DOM ---------- */
    beginTurn(fromEvent) {
        if (fromEvent) {
            if (this.turn && this.turn.preStarted) {
                // 复用 send() 预创建的容器（不重建，避免出现空壳回合）
                this.turn.preStarted = false;
            } else {
                if (this.turn) this.finalizeTurnDOM();
                this.turn = this.createTurnDOM();
            }
        } else {
            // send() 预创建：先收尾任何残留回合
            if (this.turn) this.finalizeTurnDOM();
            this.turn = this.createTurnDOM();
            this.turn.preStarted = true;
        }
        this.busy = true;
        this.turnStartedAt = Date.now();
        this.startTurnTimer();
        this.setLiveStatus('内核已接受指令…', true);
        NeuralStage.set('running');
        this.pendingInteractive = null;
    },

    ensureTurn() {
        if (!this.turn) this.beginTurn();
    },

    createTurnDOM() {
        const group = el('div', 'msg msg-assistant');
        const think = el('div', 'think-block live');
        think.dataset.open = '1';
        think.innerHTML =
            '<div class="think-head"><span class="think-icon">◈</span><span>思考过程</span>' +
            '<span class="think-toggle">−</span></div><div class="think-body"></div>';
        const tools = el('div', 'tool-stack');
        const bubble = el('div', 'msg-bubble streaming');
        const meta = el('div', 'msg-meta');
        meta.hidden = true;
        group.append(think, tools, bubble, meta);

        think.querySelector('.think-head').addEventListener('click', () => {
            const open = think.dataset.open === '1';
            think.dataset.open = open ? '0' : '1';
            think.querySelector('.think-toggle').textContent = open ? '+' : '−';
        });

        $('#chatMessages').appendChild(group);
        this.toBottom(true);
        return { group, think, thinkBody: think.querySelector('.think-body'), tools, bubble, meta };
    },

    /* ---------- 流式批处理（rAF 合并，性能关键） ---------- */
    streamQ: [],
    streamRaf: 0,

    streamPush(target, text) {
        this.streamQ.push([target, text]);
        if (!this.streamRaf) {
            this.streamRaf = requestAnimationFrame(() => this.streamFlush());
        }
    },

    streamFlush() {
        if (this.streamRaf) { cancelAnimationFrame(this.streamRaf); this.streamRaf = 0; }
        if (!this.streamQ.length || !this.turn) { this.streamQ = []; return; }
        let think = '', bubble = '';
        for (const [t, s] of this.streamQ) {
            if (t === 'think') think += s;
            else if (t === 'bubble') bubble += s;
        }
        this.streamQ = [];
        if (think) {
            this.turn.thinkBody.textContent += think;
            this.scrollThink();
        }
        if (bubble) {
            this.turn.bubble.textContent += bubble;
            this.toBottom(false);
        }
    },

    scrollThink() {
        const tb = this.turn && this.turn.thinkBody;
        if (tb) tb.scrollTop = tb.scrollHeight;
    },

    /* ---------- 工具卡片 ---------- */
    upsertTool(p, state) {
        this.ensureTurn();
        const id = p.tool_id || p.id || '';
        const name = p.name || 'tool';
        const key = id || `byname:${name}`;
        let entry = this.toolCards.get(key);

        if (!entry) {
            const card = el('div', 'tool-card');
            card.dataset.state = state;
            card.dataset.open = '1';
            const head = el('div', 'tool-head');
            head.innerHTML =
                `<span class="tool-ico">▸</span><span class="tool-name">${esc(name)}</span>` +
                `<span class="tool-label"></span><span class="tool-state"></span>`;
            const body = el('div', 'tool-body');
            card.append(head, body);
            head.addEventListener('click', () => {
                card.dataset.open = card.dataset.open === '1' ? '0' : '1';
            });
            this.turn.tools.appendChild(card);
            entry = { card, body, head, label: head.querySelector('.tool-label'), stateEl: head.querySelector('.tool-state'), name };
            this.toolCards.set(key, entry);
            if (!id) this.toolsByName.set(name, entry);
        }

        entry.card.dataset.state = state;
        entry.stateEl.textContent = state === 'running' ? '运行中' : state === 'done' ? '完成' : '失败';

        // 摘要行：context 或 args 概览
        const ctx = p.context || p.preview || '';
        if (ctx) entry.label.textContent = String(ctx).slice(0, 80);

        // body：args / result
        let detail = '';
        if (p.args && Object.keys(p.args).length) {
            detail += '$ ' + fmtArgs(name, p.args) + '\n';
        }
        if (p.result !== undefined && p.result !== null) {
            detail += String(p.result).slice(0, 4000);
        }
        if (p.error) detail += '✗ ' + String(p.error).slice(0, 2000);
        if (detail) {
            entry.body.textContent = detail;
            entry.card.dataset.open = '1';
        }
        this.toBottom(false);
    },

    /* ---------- 交互请求 ---------- */
    showApproval(p) {
        this.ensureTurn();
        const card = el('div', 'interact-card');
        const choices = Array.isArray(p.choices) ? p.choices : ['once', 'deny'];
        const labelMap = { once: '允许一次', session: '本会话允许', always: '总是允许', deny: '拒绝' };
        card.innerHTML =
            `<div class="interact-q">⚠ 需要授权执行${p.description ? `：${esc(p.description)}` : ''}\n` +
            `<span style="color:#8fd8ff;font-family:var(--mono)">${esc((p.command || '').slice(0, 500))}</span></div>`;
        const actions = el('div', 'interact-actions');
        for (const c of choices) {
            const b = el('button', 'mini-btn', labelMap[c] || c);
            b.addEventListener('click', async () => {
                if (card.classList.contains('resolved')) return;
                card.classList.add('resolved');
                try {
                    await this.rpc('approval.respond', {
                        session_id: this.sid,
                        choice: c,
                        request_id: p.request_id,
                    });
                    this.setLiveStatus(`已响应授权请求：${labelMap[c] || c}`, true);
                } catch (e) {
                    this.addSystem(`授权响应失败: ${e.message}`);
                }
            });
            actions.appendChild(b);
        }
        card.appendChild(actions);
        this.turn.group.appendChild(card);
        this.toBottom(true);
        this.setLiveStatus('⚠ 等待你的授权决定', true);
    },

    showClarify(p) {
        this.ensureTurn();
        const card = el('div', 'interact-card');
        const q = p.question || p.message || p.text || '内核需要你的补充信息';
        const qid = p.question_id || p.id || p.request_id;
        card.innerHTML = `<div class="interact-q">◈ ${esc(q)}</div>`;
        const actions = el('div', 'interact-actions');
        const opts = Array.isArray(p.options) ? p.options : [];
        if (opts.length) {
            for (const o of opts) {
                const label = typeof o === 'string' ? o : (o.label || o.value || JSON.stringify(o));
                const b = el('button', 'mini-btn', label);
                b.addEventListener('click', () => this.respondClarify(card, qid, label));
                actions.appendChild(b);
            }
        } else {
            const inp = el('input');
            inp.style.cssText = 'flex:1;background:rgba(0,0,0,.3);border:1px solid var(--line);border-radius:8px;color:var(--text);padding:7px 11px;font-size:12.5px;outline:none;min-width:200px';
            inp.placeholder = '输入回答…';
            const b = el('button', 'mini-btn', '提交');
            b.addEventListener('click', () => this.respondClarify(card, qid, inp.value));
            inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') this.respondClarify(card, qid, inp.value); });
            actions.append(inp, b);
        }
        card.appendChild(actions);
        this.turn.group.appendChild(card);
        this.toBottom(true);
        this.setLiveStatus('◈ 内核在等你回答', true);
    },

    async respondClarify(card, qid, answer) {
        if (card.classList.contains('resolved')) return;
        card.classList.add('resolved');
        try {
            await this.rpc('clarify.respond', {
                session_id: this.sid,
                question_id: qid,
                answer: String(answer || ''),
            });
            this.addSystem(`↳ 已回答：${String(answer || '').slice(0, 200)}`);
            this.setLiveStatus('已提交回答…', true);
        } catch (e) {
            this.addSystem(`回答提交失败: ${e.message}`);
        }
    },

    showError(p) {
        const txt = p.message || p.error || JSON.stringify(p);
        const d = el('div', 'msg-error', '✗ ' + String(txt).slice(0, 2000));
        $('#chatMessages').appendChild(d);
        this.toBottom(true);
        NeuralStage.set('error');
    },

    /* ---------- 回合结束 ---------- */
    endTurn(p) {
        if (!this.turn) return;
        this.streamFlush();
        const t = this.turn;
        this.stopTurnTimer();

        // bubble 收尾
        t.bubble.classList.remove('streaming');
        if (!t.bubble.textContent.trim() && p && p.text) {
            t.bubble.textContent = p.text;
        }
        if (!t.bubble.textContent.trim()) t.bubble.remove();

        // Some gateway/model combinations repeat the final answer in the
        // reasoning event. Do not present that echo as a thought trace.
        t.think.classList.remove('live');
        const trace = t.thinkBody.textContent.trim();
        const answer = t.bubble.textContent.trim();
        if (!trace || trace === answer) t.think.remove();

        // 失败态
        if (p && p.status === 'error') {
            const msg = p.error || p.text || '未知错误';
            const d = el('div', 'msg-error', '✗ ' + String(msg).slice(0, 2000));
            t.group.appendChild(d);
        }

        // usage 元信息
        const dur = ((Date.now() - this.turnStartedAt) / 1000).toFixed(1);
        const u = (p && p.usage) || {};
        const bits = [];
        if (u.model) bits.push(`<b>${esc(u.model)}</b>`);
        bits.push(`${dur}s`);
        if (u.output !== undefined) bits.push(`out ${u.output}`);
        if (u.context_percent !== undefined) bits.push(`ctx ${u.context_percent}%`);
        if (u.cache_hit_pct !== undefined) bits.push(`cache ${u.cache_hit_pct}%`);
        t.meta.innerHTML = bits.join(' · ');
        t.meta.hidden = false;

        this.busy = false;
        this.turn = null;
        this.toolCards.clear();
        NeuralStage.set(p && p.status === 'error' ? 'error' : 'complete');
        this.setLiveStatus(p && p.status === 'error' ? '执行异常 · 请检查记录' : '本次执行已完成', false);
        Pipeline.addLog(p && p.status === 'error' ? 'error' : 'success',
            p && p.status === 'error' ? 'Hermes 执行异常' : 'Hermes 已完成本次回复');
        this.toBottom(false);
    },

    finalizeTurnDOM() {
        if (this.turn) {
            this.turn.think.classList.remove('live');
            this.streamFlush();
        }
    },

    /* ---------- 计时器 / 状态行 ---------- */
    startTurnTimer() {
        this.stopTurnTimer();
        const tick = () => {
            const s = ((Date.now() - this.turnStartedAt) / 1000).toFixed(1);
            $('#liveTimer').textContent = `${s}s`;
        };
        tick();
        this.turnTimer = setInterval(tick, 200);
    },
    stopTurnTimer() {
        if (this.turnTimer) { clearInterval(this.turnTimer); this.turnTimer = null; }
        $('#liveTimer').textContent = '';
    },
    setLiveStatus(text, active, keepTimer) {
        $('#liveStatusText').textContent = text;
        $('#liveStatus').dataset.active = active ? '1' : '0';
        if (!keepTimer && !active) $('#liveTimer').textContent = '';
    },

    /* ---------- 历史渲染 ---------- */
    renderHistory(messages) {
        $('#chatMessages').innerHTML = '';
        let shown = 0;
        for (const m of messages) {
            const role = m.role || m.type || '';
            // 兼容两种字段：text（gateway 历史）/ content（部分接口）
            let content = m.text !== undefined ? m.text : m.content;
            if (Array.isArray(content)) {
                content = content.map((c) => (typeof c === 'string' ? c : (c && c.text) || '')).join('');
            }
            if (typeof content !== 'string' || !content.trim()) continue;
            if (role === 'user') {
                this.addUser(content);
                shown++;
            } else if (role === 'assistant') {
                const wrap = el('div', 'msg msg-assistant');
                const b = el('div', 'msg-bubble', content);
                wrap.appendChild(b);
                $('#chatMessages').appendChild(wrap);
                shown++;
            }
        }
        if (shown) {
            const line = el('div', 'msg msg-system');
            line.innerHTML = `<div class="sys-line dim">── 已恢复 ${shown} 条历史消息 ──</div>`;
            $('#chatMessages').appendChild(line);
        }
        this.toBottom(true);
    },

    /* ---------- 消息 DOM ---------- */
    addUser(text) {
        const w = el('div', 'msg msg-user');
        w.appendChild(el('div', 'msg-bubble', text));
        $('#chatMessages').appendChild(w);
        this.toBottom(true);
    },
    addSystem(text) {
        const w = el('div', 'msg msg-system');
        w.innerHTML = `<div class="sys-line dim">${esc(text)}</div>`;
        $('#chatMessages').appendChild(w);
        this.toBottom(true);
    },

    clearView(confirmFirst = true) {
        if (confirmFirst && this.busy) return;
        $('#chatMessages').innerHTML = '';
        this.addSystem('◢ 界面已清屏（会话记忆仍在，刷新页面可恢复历史）');
        NeuralStage.set('idle');
    },

    /* ---------- 发送 ---------- */
    async send() {
        const inp = $('#chatInput');
        const text = inp.value.trim();
        if (!text) return;
        if (!this.ready || !this.sid) { this.addSystem('会话未就绪，请稍候…'); return; }
        if (this.busy) { this.addSystem('上一条指令还在执行中，请稍候…'); return; }

        inp.value = '';
        inp.style.height = 'auto';
        this.addUser(text);
        this.beginTurn(false);
        try {
            const r = await this.rpc('prompt.submit', { session_id: this.sid, text });
            if (r && r.status === 'queued') this.setLiveStatus('已入队…', true);
        } catch (e) {
            this.showError({ message: `发送失败: ${e.message}` });
            this.endTurn({ status: 'error', error: `发送失败: ${e.message}` });
        }
    },

    /* ---------- 滚动 ---------- */
    autoScroll: true,
    toBottom(force) {
        const box = $('#chatScroll');
        if (force || this.autoScroll) {
            box.scrollTop = box.scrollHeight;
        }
    },
};


export { Hermes };
