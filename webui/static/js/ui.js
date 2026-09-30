/**
 * WebUI 共享 UI 工具（Phase 12 从 app.js 拆出）。
 *  · DOM 选择器 / 安全文本 / 时间与体积格式化；
 *  · NeuralStage：大脑中枢的对外状态标签（neural_v4.js 也依赖它）；
 *  · 状态与阶段的唯一展示口径（前端不再用字符串包含推断业务状态）。
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


/* ── Phase 12：canonical 状态展示口径 ─────────────────────────── */

/* 后端 JobState 的 13 个主线态 + 4 个旁路态；前端只做展示，判断一律用后端给的布尔量 */
const CANONICAL_STAGES = ['PLANNING', 'RESEARCHING', 'SCRIPTING', 'PREFLIGHT', 'GENERATING',
    'QA', 'REPAIRING', 'COMPOSING', 'PACKAGING', 'READY', 'PUBLISHING', 'LEARNING', 'DONE'];
const CANONICAL_SIDE = ['PAUSED', 'BLOCKED', 'FAILED', 'CANCELLED'];

const STAGE_LABELS_CN = {
    PLANNING: '创建任务', RESEARCHING: '热点研究', SCRIPTING: '创意策划', PREFLIGHT: '分镜预检',
    GENERATING: '视频生成', QA: '自动质检', REPAIRING: '修复重做', COMPOSING: '后期合成',
    PACKAGING: '打包物料', READY: '待发布', PUBLISHING: '发布中', LEARNING: '表现学习',
    DONE: '已完成', PAUSED: '已暂停', BLOCKED: '需人工', FAILED: '失败', CANCELLED: '已取消',
};

/* 状态 → 视觉档位（ok/warn/bad/idle），同样只是展示 */
const STATE_TONE = {
    DONE: 'ok', READY: 'ok', PUBLISHING: 'ok', LEARNING: 'ok',
    PAUSED: 'warn', BLOCKED: 'bad', FAILED: 'bad', CANCELLED: 'idle',
};

function stateLabel(status) {
    return STAGE_LABELS_CN[status] || status || '—';
}

function stateTone(status) {
    if (STATE_TONE[status]) return STATE_TONE[status];
    return CANONICAL_STAGES.includes(status) ? 'ok' : 'idle';
}

function stageLabel(stage) {
    return STAGE_LABELS_CN[String(stage || '').toUpperCase()] || (stage || '—');
}

function fmtCost(value) {
    if (value == null || Number.isNaN(Number(value))) return '—';
    return '¥' + Number(value).toFixed(2);
}

function fmtPct(value) {
    if (value == null || Number.isNaN(Number(value))) return '—';
    return (Number(value) * 100).toFixed(1) + '%';
}

export {
    $, $$, el, esc, fmtTime, fmtBytes, NeuralStage,
    CANONICAL_STAGES, CANONICAL_SIDE, STAGE_LABELS_CN,
    stateLabel, stateTone, stageLabel, fmtCost, fmtPct,
};
