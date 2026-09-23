/**
 * 轻便侠·AI视频工厂 控制台前端
 */

// 状态
const state = {
    running: false,
    currentStage: null,
    progress: 0,
    stats: {},
    settings: {
        realPublish: false,
        realEngage: false,
        dailyTarget: 3,
    },
};

// DOM 元素
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    loadState();
    loadOutputs();
    setupEventListeners();
    startSSE();
    setInterval(loadState, 5000);
    setInterval(loadOutputs, 30000);
});

// 加载状态
async function loadState() {
    try {
        const resp = await fetch('/api/state');
        const data = await resp.json();
        
        state.running = data.run.running;
        state.currentStage = data.run.current_stage;
        state.progress = data.run.progress;
        state.stats = data.stats;
        state.settings = {
            realPublish: data.console.real_publish,
            realEngage: data.console.real_engage,
            dailyTarget: data.console.daily_target,
        };
        
        updateUI();
    } catch (e) {
        console.error('加载状态失败:', e);
    }
}

// 更新界面
function updateUI() {
    // 状态胶囊
    const statusPill = $('#statusPill');
    const statusText = statusPill.querySelector('.status-text');
    if (state.running) {
        statusPill.classList.add('running');
        statusText.textContent = '运行中';
    } else {
        statusPill.classList.remove('running');
        statusText.textContent = '就绪';
    }
    
    // 进度环
    const ringProgress = $('#ringProgress');
    const circumference = 2 * Math.PI * 45;
    ringProgress.style.strokeDashoffset = circumference * (1 - state.progress / 100);
    $('#ringPercent').textContent = `${Math.round(state.progress)}%`;
    
    // 流水线阶段
    const stages = ['trend', 'copy', 'storyboard', 'generate', 'compose', 'publish'];
    const currentIdx = stages.indexOf(state.currentStage);
    
    $$('.stage').forEach((el, idx) => {
        el.classList.remove('active', 'completed');
        if (state.running) {
            if (idx < currentIdx) {
                el.classList.add('completed');
            } else if (idx === currentIdx) {
                el.classList.add('active');
            }
        }
    });
    
    // 当前阶段
    const stageNames = {
        trend: '热点爆款',
        copy: '文案生成',
        storyboard: '智能分镜',
        generate: '视频生成',
        compose: '合成字幕',
        publish: '发布互动',
    };
    $('#currentStage').textContent = stageNames[state.currentStage] || '-';
    
    // 产量看板
    $('#statTrends').textContent = state.stats.trends_total || 0;
    $('#statPending').textContent = state.stats.jobs_pending || 0;
    $('#statReady').textContent = state.stats.jobs_ready || 0;
    $('#statPublished').textContent = state.stats.jobs_published || 0;
    
    // 底栏
    $('#footerQueue').textContent = state.stats.jobs_ready || 0;
    
    // 设置表单
    $('#settingRealPublish').checked = state.settings.realPublish;
    $('#settingRealEngage').checked = state.settings.realEngage;
    $('#settingDailyTarget').value = state.settings.dailyTarget;
}

// 事件监听
function setupEventListeners() {
    // 启动按钮
    $('#btnStart').addEventListener('click', async () => {
        if (state.running) {
            addMessage('system', '已有任务在运行中');
            return;
        }
        
        try {
            const resp = await fetch('/api/start', { method: 'POST' });
            const data = await resp.json();
            if (data.ok) {
                addMessage('system', '🚀 全流程已启动！');
                state.running = true;
                updateUI();
            } else {
                addMessage('system', `启动失败: ${data.error}`);
            }
        } catch (e) {
            addMessage('system', `启动失败: ${e.message}`);
        }
    });
    
    // 设置按钮
    $('#btnSettings').addEventListener('click', () => {
        $('#settingsModal').classList.add('active');
    });
    
    $('#btnCloseSettings').addEventListener('click', () => {
        $('#settingsModal').classList.remove('active');
    });
    
    $('#btnCancelSettings').addEventListener('click', () => {
        $('#settingsModal').classList.remove('active');
    });
    
    $('#btnSaveSettings').addEventListener('click', async () => {
        const settings = {
            real_publish: $('#settingRealPublish').checked,
            real_engage: $('#settingRealEngage').checked,
            daily_target: parseInt($('#settingDailyTarget').value) || 3,
        };
        
        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings),
            });
            $('#settingsModal').classList.remove('active');
            addMessage('system', '设置已保存');
            loadState();
        } catch (e) {
            addMessage('system', `保存失败: ${e.message}`);
        }
    });
    
    // 聊天输入
    $('#chatInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChat();
        }
    });
    
    $('#btnSend').addEventListener('click', sendChat);
    
    // 清空对话
    $('#btnClearChat').addEventListener('click', () => {
        const messages = $('#consoleMessages');
        messages.innerHTML = `
            <div class="message system">
                <div class="message-content">对话已清空。</div>
            </div>
        `;
    });
}

// 发送聊天
async function sendChat() {
    const input = $('#chatInput');
    const text = input.value.trim();
    if (!text) return;
    
    addMessage('user', text);
    input.value = '';
    
    // TODO: 接入 Hermes API
    addMessage('assistant', '收到指令，正在处理...');
}

// 添加消息
function addMessage(type, content) {
    const messages = $('#consoleMessages');
    const div = document.createElement('div');
    div.className = `message ${type}`;
    div.innerHTML = `<div class="message-content">${escapeHtml(content)}</div>`;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

// 添加日志
function addLog(level, message) {
    const container = $('#logsContainer');
    const div = document.createElement('div');
    div.className = `log-item ${level}`;
    div.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    container.appendChild(div);
    
    // 保持最多100条
    while (container.children.length > 100) {
        container.removeChild(container.firstChild);
    }
    
    container.scrollTop = container.scrollHeight;
}

// SSE 实时日志
function startSSE() {
    const eventSource = new EventSource('/api/logs');
    
    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'status') {
                // 状态更新
                state.running = data.data.running;
                state.currentStage = data.data.current_stage;
                state.progress = data.data.progress;
                updateUI();
            } else if (data.type === 'log') {
                // 日志消息
                addLog(data.level || 'info', data.message);
            }
        } catch (e) {
            // 普通文本日志
            addLog('info', event.data);
        }
    };
    
    eventSource.onerror = () => {
        console.log('SSE 连接断开，5秒后重连...');
        eventSource.close();
        setTimeout(startSSE, 5000);
    };
}

// 加载最新产出
async function loadOutputs() {
    try {
        const resp = await fetch('/api/outputs?limit=4');
        const outputs = await resp.json();
        
        const grid = $('#outputsGrid');
        if (outputs.length === 0) {
            grid.innerHTML = '<div class="output-placeholder">暂无成片</div>';
            return;
        }
        
        grid.innerHTML = outputs.map(o => `
            <div class="output-item" title="${escapeHtml(o.name)}">
                ${o.thumb ? `<img src="${o.thumb}?t=${Date.now()}" alt="${escapeHtml(o.name)}" loading="lazy">` : ''}
                <div class="output-name">${escapeHtml(o.name)}</div>
            </div>
        `).join('');
    } catch (e) {
        console.error('加载产出失败:', e);
    }
}

// HTML 转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
