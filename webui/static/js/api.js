/**
 * WebUI 与后端通信的唯一出口（Phase 12）。
 *
 * 所有业务数据都来自 canonical API（JobStore/Orchestrator），
 * 前端不做任何"看脚本输出猜状态"的逻辑。
 */
'use strict';

async function request(url, options) {
    const response = await fetch(url, options);
    let payload = null;
    try {
        payload = await response.json();
    } catch (e) {
        payload = null;
    }
    if (!response.ok) {
        const detail = (payload && (payload.detail || payload.error)) || ('HTTP ' + response.status);
        const err = new Error(detail);
        err.status = response.status;
        err.payload = payload;
        throw err;
    }
    if (payload && payload.ok === false) {
        const err = new Error(payload.error || payload.detail || '请求被拒绝');
        err.status = response.status;
        err.payload = payload;
        throw err;
    }
    return payload;
}

function getJSON(url) {
    return request(url, { method: 'GET' });
}

function postJSON(url, body) {
    return request(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body === undefined ? {} : body),
    });
}

/* ── 任务 API ────────────────────────────────────────────────── */

function listJobs(params) {
    const qs = new URLSearchParams();
    const p = params || {};
    if (p.status) qs.set('status', p.status);
    if (p.q) qs.set('q', p.q);
    qs.set('limit', String(p.limit || 20));
    return getJSON('/api/jobs?' + qs.toString());
}

function createJobs(body) {
    return postJSON('/api/jobs', body || {});
}

function jobDetail(uid) {
    return getJSON('/api/jobs/' + encodeURIComponent(uid));
}

function jobArtifacts(uid) {
    return getJSON('/api/jobs/' + encodeURIComponent(uid) + '/artifacts');
}

function jobEvents(uid, since) {
    const qs = since ? ('?since=' + encodeURIComponent(since)) : '';
    return getJSON('/api/jobs/' + encodeURIComponent(uid) + '/events' + qs);
}

function jobAction(uid, action, body) {
    return postJSON('/api/jobs/' + encodeURIComponent(uid) + '/' + action, body || {});
}

function materials(limit) {
    return getJSON('/api/materials?limit=' + encodeURIComponent(limit || 12));
}

function systemHealth() {
    return getJSON('/api/system/health');
}

/**
 * 结构化 job 事件流（SSE）。
 * handlers: { onJob(event), onSnapshot(run), onError(err) }
 */
function openJobEvents(handlers) {
    const h = handlers || {};
    let source;
    try {
        source = new EventSource('/api/jobs/events');
    } catch (e) {
        if (h.onError) h.onError(e);
        return null;
    }
    source.addEventListener('job', (ev) => {
        try { if (h.onJob) h.onJob(JSON.parse(ev.data)); } catch (e) { /* 忽略坏帧 */ }
    });
    source.addEventListener('snapshot', (ev) => {
        try { if (h.onSnapshot) h.onSnapshot(JSON.parse(ev.data)); } catch (e) { /* 忽略坏帧 */ }
    });
    source.onerror = (err) => { if (h.onError) h.onError(err); };
    return source;
}

export {
    getJSON, postJSON,
    listJobs, createJobs, jobDetail, jobArtifacts, jobEvents, jobAction,
    materials, systemHealth, openJobEvents,
};
