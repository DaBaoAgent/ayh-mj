/**
 * 轻便侠·AI视频工厂 控制台前端（Phase 12）。
 *
 * 这里只做装配与启动：api / store / hermes / jobs / settings / outputs / health
 * 各自独立成模块，前端不再通过字符串包含"失败/完成"来推断业务状态。
 */
'use strict';

import { $, $$, el, NeuralStage } from './js/ui.js';
import { Pipeline, Jobs } from './js/jobs.js';
import { Hermes } from './js/hermes.js';
import { Settings } from './js/settings.js';
import { Outputs } from './js/outputs.js';
import { Health } from './js/health.js';
import { openJobEvents } from './js/api.js';
import './neural_v4.js';

function debounce(fn, ms) {
    let timer = null;
    return function debounced() {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => { timer = null; fn(); }, ms);
    };
}

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

    // 任务台
    const jobFilter = $('#jobsFilter');
    if (jobFilter) {
        jobFilter.addEventListener('change', () => Jobs.load({ filter: jobFilter.value }));
    }
    const jobRefresh = $('#jobsRefresh');
    if (jobRefresh) jobRefresh.addEventListener('click', () => Jobs.load());
    const jobClose = $('#btnCloseJob');
    if (jobClose) jobClose.addEventListener('click', () => Jobs.close());
    const jobMask = $('#jobMask');
    if (jobMask) jobMask.addEventListener('click', () => Jobs.close());

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
    // 键盘快捷键：Esc 关设置/任务详情
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { Settings.close(); Jobs.close(); }
    });
}

const refreshFromEvents = debounce(() => { Pipeline.refresh(); Jobs.load(); }, 700);

function boot() {
    bindUI();
    // 会话 cwd 必须来自服务端注入的项目根（window.__AYHMJ_ROOT__），前端不硬编码本机路径。
    Hermes.setRoot(window.__AYHMJ_ROOT__);
    NeuralStage.init();
    Hermes.connect();
    Pipeline.refresh();
    Pipeline.startSSE();
    Jobs.load();
    Outputs.load();
    Health.load();
    setInterval(() => Pipeline.refresh(), 4000);
    setInterval(() => Jobs.load(), 8000);
    setInterval(() => Outputs.load(), 30000);
    setInterval(() => Health.load(), 60000);
    openJobEvents({
        onSnapshot: (run) => Pipeline.apply({ run: run }),
        onJob: () => refreshFromEvents(),
    });
}

document.addEventListener('DOMContentLoaded', boot);
