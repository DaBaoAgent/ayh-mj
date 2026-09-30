/**
 * 前端共享状态容器（Phase 12）。
 *
 * 只为"同一份事实渲染到多个面板"服务，不含任何业务推断：
 * 状态怎么变由 canonical API 决定，这里只是最后一次服务端响应的缓存。
 */
'use strict';

function createStore(initial) {
    let state = Object.assign({
        run: null,
        jobs: [],
        jobsTotal: null,
        filter: '',
        selectedUid: null,
        detail: null,
        materials: [],
        outputs: [],
        health: null,
    }, initial || {});
    let subscribers = [];
    return {
        get() { return state; },
        set(patch) {
            state = Object.assign({}, state, patch || {});
            for (const fn of subscribers) {
                try { fn(state); } catch (e) { console.error('store subscriber failed', e); }
            }
            return state;
        },
        subscribe(fn) {
            subscribers.push(fn);
            return () => { subscribers = subscribers.filter((f) => f !== fn); };
        },
    };
}

const Store = createStore();

export { Store, createStore };
