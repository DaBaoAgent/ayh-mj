/**
 * 轻便侠·AI视频工厂 控制台前端 v4
 *  · Hermes 控制台：WS 桥接到 hermes serve（与桌面版本体同源）
 *    事件渲染完整对齐桌面版语义：思考过程 / 工具调用 / 回复流 / 交互请求
 *  · 流水线：SSE 实时日志 + 状态轮询
 *  · 设置抽屉：后端 schema 驱动自动渲染
 */
'use strict';

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
}
function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
}
function fmtTime(iso) {
    const d = iso ? new Date(iso) : new Date();
    return d.toTimeString().slice(0, 8);
}
function fmtBytes(n) {
    if (n > 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB';
    if (n > 1024) return (n / 1024).toFixed(0) + ' KB';
    return n + ' B';
}

/* The visual renderer extends this state controller in neural_v4.js. */
const NeuralStage = {
    mode: 'idle',

    set(mode, text) {
        this.mode = mode;
        const stage = $('#neuralStage');
        if (!stage) return;
        stage.dataset.mode = mode;
        const label = {
            idle: ['NEURAL CORE / STANDBY', '等待创作指令', '神经网络已同步，随时开始一条视频任务'],
            running: ['NEURAL CORE / EXECUTING', '正在编排创意信号', '执行摘要与工具进度正在下方实时汇聚'],
            thinking: ['NEURAL CORE / ANALYSING', '正在解析任务上下文', '公开执行摘要正在同步'],
            tool: ['NEURAL CORE / TOOL LINK', '正在调度生产工具', '数据流已接入，等待工具回传'],
            complete: ['NEURAL CORE / COMPLETE', '创作链路已完成', '回复与产出已归档到本次执行记录'],
            error: ['NEURAL CORE / INTERRUPTED', '执行链路需要注意', '请检查下方错误信息后重新发起任务'],
        }[mode] || [];
        $('#neuralPhase').textContent = label[0] || '';
        $('#neuralTitle').textContent = text || label[1] || '';
        $('#neuralHint').textContent = label[2] || '';
    },

};

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
    reconnectTimer: null,
    turnTimer: null,
    turnStartedAt: 0,
    pendingInteractive: null,   // 当前交互请求（approval/clarify）

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
                cwd: 'D:/@kaifa/ayh-mj',
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
            const r = await this.rpc('session.create', { cwd: 'D:/@kaifa/ayh-mj' });
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
        $('#statusText').textContent = this.running
            ? `运行中 · ${this.stageName(run.current_stage) || ''}`
            : (run.message === '完成' ? '待命' : (run.message || '就绪'));

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
        $('#renderState').textContent = this.running ? (this.stageName(run.current_stage) || '正在启动')
            : (run.message === '完成' ? '上一任务完成' : '等待任务');

        // 阶段状态
        const curIdx = this.stages.indexOf(run.current_stage);
        $$('.stage').forEach((elm, idx) => {
            let st = 'idle', mark = '·';
            if (this.running && curIdx >= 0) {
                if (idx < curIdx) { st = 'done'; mark = '✓'; }
                else if (idx === curIdx) { st = 'active'; mark = '▶'; }
            } else if (!this.running && run.message === '完成' && prog >= 100) {
                st = 'done'; mark = '✓';
            } else if (!this.running && run.message && run.message.includes('失败')) {
                if (idx === curIdx) { st = 'error'; mark = '✗'; }
            }
            elm.dataset.state = st;
            elm.querySelector('.stage-state').textContent = mark;
        });

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
        const map = { trend: '热点雷达', copy: '创意策划', storyboard: '智能分镜',
                      generate: '视频生成', compose: '合成发布', publish: '效果追踪' };
        return map[id] || '';
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
 * 三、最新产出
 * ================================================================ */
async function loadOutputs() {
    try {
        const response = await fetch('/api/outputs?limit=3');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const outputs = await response.json();
        const grid = $('#outputsGrid');
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
            meta.appendChild(el('div', 'output-sub', `${fmtBytes(o.size)} · ${String(o.mtime).slice(5, 16).replace('T', ' ')}`));
            item.appendChild(meta);
            grid.appendChild(item);
        }
    } catch { /* ignore */ }
}

/* ================================================================
 * 四、设置抽屉（schema 驱动）
 * ================================================================ */
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
            Pipeline.refresh();
        } catch (e) {
            hint.textContent = `保存失败: ${e.message}`;
            hint.className = 'save-hint show err';
        }
    },
};

/* ================================================================
 * 五、事件绑定 & 启动
 * ================================================================ */
function bindUI() {
    // 顶栏
    $('#btnStart').addEventListener('click', async () => {
        $('#btnStart').disabled = true;
        try {
            const r = await fetch('/api/start', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
            }).then((x) => x.json());
            if (r.error) Hermes.addSystem(`启动失败：${r.error}`);
        } catch (e) {
            Hermes.addSystem(`启动失败：${e.message}`);
        }
        setTimeout(() => Pipeline.refresh(), 800);
    });
    $('#btnStop').addEventListener('click', async () => {
        await fetch('/api/stop', { method: 'POST' }).catch(() => {});
        setTimeout(() => Pipeline.refresh(), 800);
    });

    // 设置抽屉
    $('#btnSettings').addEventListener('click', () => Settings.open());
    $('#btnCloseSettings').addEventListener('click', () => Settings.close());
    $('#btnSaveSettings').addEventListener('click', () => Settings.save());
    $('#drawerMask').addEventListener('click', () => Settings.close());

    // 控制台
    $('#btnSend').addEventListener('click', () => Hermes.send());
    $('#btnNewChat').addEventListener('click', () => Hermes.newChat());
    $('#btnClearView').addEventListener('click', () => Hermes.clearView());

    const ta = $('#chatInput');
    ta.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            Hermes.send();
        }
    });
    ta.addEventListener('input', () => {
        ta.style.height = 'auto';
        ta.style.height = Math.min(ta.scrollHeight, 150) + 'px';
    });

    // 滚动跟随
    const box = $('#chatScroll');
    box.addEventListener('scroll', () => {
        const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 90;
        Hermes.autoScroll = nearBottom;
        $('#jumpBottom').hidden = nearBottom;
    });
    $('#jumpBottom').addEventListener('click', () => {
        Hermes.autoScroll = true;
        box.scrollTop = box.scrollHeight;
        $('#jumpBottom').hidden = true;
    });
    // 键盘快捷键：Esc 关设置
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') Settings.close();
    });
}

function boot() {
    bindUI();
    NeuralStage.init();
    Hermes.connect();
    Pipeline.refresh();
    Pipeline.startSSE();
    loadOutputs();
    setInterval(() => Pipeline.refresh(), 4000);
    setInterval(loadOutputs, 30000);
}

document.addEventListener('DOMContentLoaded', boot);
