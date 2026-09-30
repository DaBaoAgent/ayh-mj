"""Phase 12：WebUI 源码护栏 —— 模块拆分 + 状态判断只用 canonical 事实。

前端"不猜状态"这条验收标准，靠静态扫描守：任何"用字符串包含/相等去推断核心业务状态"
的写法都会让测试失败，而不是等人工 review 才发现。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from lib.jobstore import JobState

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent.parent
STATIC = ROOT / "webui" / "static"
JS_DIR = STATIC / "js"
TEMPLATE = ROOT / "webui" / "templates" / "index.html"

REQUIRED_MODULES = ("api", "store", "hermes", "jobs", "settings", "outputs", "health", "ui")
MAX_ASSEMBLY_BYTES = 12_000

CJK = r"[\u3000-\u9fff\uff00-\uffef]"
def _prose_literal(name: str) -> str:
    """一个"含中文的字面量"（单引号或双引号，各自配对）。"""
    q = f"(?P<{name}>['\"])"
    return q + r"(?:(?!(?P=" + name + r")).)*?" + CJK + \
        r"(?:(?!(?P=" + name + r")).)*?(?P=" + name + r")"


# 只有"字面量直接当比较/包含操作数"才算状态推断；展示用三元表达式不算
_PROSE_CALL = re.compile(
    r"\.\s*(?:includes|indexOf|startsWith|endsWith|search|test)\s*\(\s*"
    + _prose_literal("qa"))
_PROSE_COMPARE = re.compile(
    r"(?:[=!]==?\s*" + _prose_literal("qc")
    + r"|" + _prose_literal("qd") + r"\s*[=!]==?)")
_MESSAGE_PARSING = re.compile(r"\b(message|msg|text|log)\b\s*\.\s*(includes|indexOf|search|test)\b")


def _js_files() -> list[Path]:
    return sorted(JS_DIR.glob("*.js")) + [STATIC / "app.js", STATIC / "neural_v4.js"]


def test_frontend_never_infers_business_state_from_prose():
    """核心规则：不许用中文状态词做包含/相等判断（状态只能来自 canonical 字段）。"""
    offenders: list[str] = []
    for path in _js_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("*", "//", "/*")):
                continue
            hit = _PROSE_CALL.search(line) or _PROSE_COMPARE.search(line)
            if hit:
                offenders.append(f"{path.name}:{lineno}: {stripped[:120]} -> {hit.group(0)}")
    assert not offenders, "前端用字符串状态推断业务状态：\n" + "\n".join(offenders)


def test_frontend_does_not_parse_run_message_or_logs():
    offenders = []
    for path in _js_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "run.message" in line and re.search(r"if\s*\(|==|!=|includes\(|indexOf\(", line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()[:120]}")
            if _MESSAGE_PARSING.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()[:120]}")
    assert not offenders, "前端在解析 message/日志字符串来推断状态：\n" + "\n".join(offenders)


def test_app_js_is_only_an_assembly_layer():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    for module in ("api", "hermes", "jobs", "settings", "outputs", "health", "ui"):
        assert f"'./js/{module}.js'" in app, f"app.js 没有装配 {module} 模块"
    assert "'./neural_v4.js'" in app
    assert app.count("import ") >= 7
    assert len(app.encode("utf-8")) < MAX_ASSEMBLY_BYTES, "app.js 又长回去了"
    hermes = (JS_DIR / "hermes.js").read_text(encoding="utf-8")
    assert len(hermes) > 5 * len(app)          # 大块逻辑确实搬进了模块，没留在装配层


def test_store_is_the_single_frontend_state_container():
    assert (JS_DIR / "store.js").exists()
    for module in ("jobs", "outputs", "health"):
        source = (JS_DIR / f"{module}.js").read_text(encoding="utf-8")
        assert "from './store.js'" in source, f"{module}.js 没走共享 store"
    # 设置面板不自己维护任务事实：保存后只让 Pipeline 用 canonical 接口刷新
    settings = (JS_DIR / "settings.js").read_text(encoding="utf-8")
    assert "from './jobs.js'" in settings and "Pipeline.refresh" in settings


def test_modules_exist_and_export_their_panels():
    expected = {"api": ["request", "listJobs", "jobAction", "openJobEvents"],
                "store": ["createStore", "Store"],
                "jobs": ["Pipeline", "Jobs"],
                "settings": ["Settings"],
                "outputs": ["Outputs"],
                "health": ["Health"],
                "hermes": ["Hermes"],
                "ui": ["stateLabel", "stageLabel", "CANONICAL_STAGES"]}
    for module, symbols in expected.items():
        source = (JS_DIR / f"{module}.js").read_text(encoding="utf-8")
        for symbol in symbols:
            assert symbol in source, f"{module}.js 缺少 {symbol}"


def test_frontend_canonical_states_match_backend_state_machine():
    source = (JS_DIR / "ui.js").read_text(encoding="utf-8")
    linear = re.search(r"CANONICAL_STAGES = \[(.*?)\]", source, re.S)
    side = re.search(r"CANONICAL_SIDE = \[(.*?)\]", source, re.S)
    assert linear and side
    assert tuple(re.findall(r"'([A-Z_]+)'", linear.group(1))) == JobState.LINEAR
    assert tuple(re.findall(r"'([A-Z_]+)'", side.group(1))) == JobState.SIDE
    for state in JobState.ALL:                 # 每个状态都要有中文展示名，不裸奔状态码
        assert f"{state}:" in source, f"缺少 {state} 的展示文案"


def test_jobs_module_renders_state_through_helpers():
    source = (JS_DIR / "jobs.js").read_text(encoding="utf-8")
    assert "stateLabel(" in source and "stateTone(" in source and "stageLabel(" in source
    assert "jobs_by_status" in source           # 流水线只用状态计数
    assert "actions.retry" in source and "actions.cancel" in source


def test_settings_module_shows_runtime_and_ignored_fields():
    source = (JS_DIR / "settings.js").read_text(encoding="utf-8")
    assert "renderRuntime" in source and "runtimeBox" in source
    assert "ignored" in source and "runtime_applies_to" in source


def test_outputs_module_renders_material_facts():
    source = (JS_DIR / "outputs.js").read_text(encoding="utf-8")
    for key in ("video_url", "qa", "publish", "performance", "blocked"):
        assert key in source, key


def test_template_wires_phase12_panels():
    html = TEMPLATE.read_text(encoding="utf-8")
    for anchor in ('id="stateStrip"', 'id="jobsList"', 'id="jobsFilter"', 'id="jobsRefresh"',
                   'id="healthGrid"', 'id="healthStatus"', 'id="materialsList"',
                   'id="jobDrawer"', 'id="jobMask"', 'id="btnCloseJob"', 'id="runtimeBox"',
                   "phase12.css"):
        assert anchor in html, f"index.html 缺少 {anchor}"
    assert 'type="module"' in html and "/static/app.js" in html


def test_neural_v4_uses_shared_ui_module():
    source = (STATIC / "neural_v4.js").read_text(encoding="utf-8")
    assert "from './js/ui.js'" in source and "NeuralStage" in source
    assert "export { MatrixRain }" in source
