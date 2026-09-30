"""编排层异常与 error taxonomy（Phase 3 落地 → Phase 4 补全为完整清单）。

约定
  · 每个异常都带稳定 `error_code`（UPPERCASE）；落进 `jobs.error_code` /
    `attempts.error_code` / `provider_tasks`。前端、RepairEngine、审计只认这个码，
    绝不解析中文 message —— 否则"文案一改，告警就哑"。
  · `RETRYABLE_CODES` 决定是否允许"同阶段重试"；`TRANSIENT_CODES` 额外要求
    指数退避（这是网络抖动，不是业务错误）；业务错误永远不允许网络式无限重试。
  · `REPAIR_MAP` 把 error_code 映射到**白名单动作**；RepairEngine 只在这个表里取
    动作，表外一律 ABORT（Phase 4 必做任务 8/9）。
"""
from __future__ import annotations

# ── 完整 error taxonomy（Phase 4：20 个业务码 + 编排内部码）─────────────────
# 配置 / 凭据
CONFIG_MISSING = "CONFIG_MISSING"
AUTH_EXPIRED = "AUTH_EXPIRED"
# 网络 / 限流
NETWORK_TRANSIENT = "NETWORK_TRANSIENT"
RATE_LIMIT = "RATE_LIMIT"
# 输入
PROMPT_TOO_LONG = "PROMPT_TOO_LONG"
ASSET_MISSING = "ASSET_MISSING"
# 供应商
PROVIDER_REJECTED = "PROVIDER_REJECTED"
GENERATION_FAILED = "GENERATION_FAILED"
GENERATION_TIMEOUT = "GENERATION_TIMEOUT"
DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
# 质检
ASR_MISMATCH = "ASR_MISMATCH"
SUBTITLE_ALIGN_FAIL = "SUBTITLE_ALIGN_FAIL"
VISUAL_QA_FAIL = "VISUAL_QA_FAIL"
PRODUCT_DEFORMED = "PRODUCT_DEFORMED"
WRONG_SPEAKER = "WRONG_SPEAKER"
HUMAN_ANATOMY_FAIL = "HUMAN_ANATOMY_FAIL"
# 合规
COMPLIANCE_BLOCK = "COMPLIANCE_BLOCK"
# 发布
PUBLISH_QUOTA = "PUBLISH_QUOTA"
PUBLISH_AUTH = "PUBLISH_AUTH"
PACKAGING_INCOMPLETE = "PACKAGING_INCOMPLETE"        # packaging artifact 缺失/不完整
AI_DISCLOSURE_UNCONFIRMED = "AI_DISCLOSURE_UNCONFIRMED"  # AI 声明无法确认 → 不许 direct 发布
REQUIRE_HUMAN_PUBLISH = "REQUIRE_HUMAN_PUBLISH"      # 需要人工确认/人工发布
PLATFORM_PAUSED = "PLATFORM_PAUSED"                  # 平台因凭据/账号异常被熔断暂停
NOT_READY = "NOT_READY"                              # 任务还没到 READY，不能发布
ENGAGE_CIRCUIT_OPEN = "ENGAGE_CIRCUIT_OPEN"          # 自动互动熔断（连续异常/超频）
# 兜底
UNKNOWN = "UNKNOWN"

BUSINESS_CODES: tuple[str, ...] = (
    CONFIG_MISSING, AUTH_EXPIRED, NETWORK_TRANSIENT, RATE_LIMIT, PROMPT_TOO_LONG,
    ASSET_MISSING, PROVIDER_REJECTED, GENERATION_FAILED, GENERATION_TIMEOUT,
    DOWNLOAD_FAILED, ASR_MISMATCH, SUBTITLE_ALIGN_FAIL, VISUAL_QA_FAIL,
    PRODUCT_DEFORMED, WRONG_SPEAKER, HUMAN_ANATOMY_FAIL, COMPLIANCE_BLOCK,
    PUBLISH_QUOTA, PUBLISH_AUTH, UNKNOWN,
)

# ── 编排内部码（阶段机/预算/取消，不算"业务失败"）────────────────────────
ORCHESTRATOR_ERROR = "ORCHESTRATOR_ERROR"
NO_SPEC = "NO_SPEC"
PLAN_FAILED = "PLAN_FAILED"                    # 自主规划失败（Phase 5）
PROMPT_NOT_COMPILED = "PROMPT_NOT_COMPILED"     # StorySpec 就绪但 H3 prompt 未编译（Phase 7 前）
# Phase 7：编译/路由阶段的门
PROMPT_BUDGET_EXCEEDED = "PROMPT_BUDGET_EXCEEDED"  # 编译期就算出超限（压缩也压不下来）
WORKFLOW_INCOMPATIBLE = "WORKFLOW_INCOMPATIBLE"    # 没有工作流能保住全部关键能力 → 拒绝提交
PRESCREEN_REQUIRED = "PRESCREEN_REQUIRED"          # 高风险新构图必须先过 5s 预筛
PRESCREEN_FAILED = "PRESCREEN_FAILED"              # 预筛未过 → 不允许跑 15s 正式片
# 合规（Phase 6）：LLM 文案出现未登记/待核验/禁止的产品承诺
CLAIM_UNMAPPED = "CLAIM_UNMAPPED"                  # 数值/认证/疗效表述映射不到 claim_id
CLAIM_NEEDS_VERIFICATION = "CLAIM_NEEDS_VERIFICATION"  # 命中 needs_verification 口径
CLAIM_FORBIDDEN = "CLAIM_FORBIDDEN"               # 命中禁用改写/绝对化/价格政策红线
MISSING_INPUT = "MISSING_INPUT"
PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
QA_FAILED = "QA_FAILED"
COMPOSE_FAILED = "COMPOSE_FAILED"
PACKAGE_FAILED = "PACKAGE_FAILED"
STAGE_TIMEOUT = "STAGE_TIMEOUT"
STAGE_FAILED = "STAGE_FAILED"
STAGE_NOT_REGISTERED = "STAGE_NOT_REGISTERED"
UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
CANCEL_REQUESTED = "CANCEL_REQUESTED"
BLOCKED_BUDGET = "BLOCKED_BUDGET"
CAPABILITY_BLOCKED = "CAPABILITY_BLOCKED"
UNKNOWN_JOB = "UNKNOWN_JOB"
JOB_NOT_RESUMABLE = "JOB_NOT_RESUMABLE"

INTERNAL_CODES: tuple[str, ...] = (
    ORCHESTRATOR_ERROR, NO_SPEC, PLAN_FAILED, PROMPT_NOT_COMPILED,
    PROMPT_BUDGET_EXCEEDED, WORKFLOW_INCOMPATIBLE, PRESCREEN_REQUIRED, PRESCREEN_FAILED,
    CLAIM_UNMAPPED, CLAIM_NEEDS_VERIFICATION, CLAIM_FORBIDDEN,
    MISSING_INPUT, PREFLIGHT_FAILED, QA_FAILED,
    COMPOSE_FAILED, PACKAGE_FAILED, STAGE_TIMEOUT, STAGE_FAILED,
    STAGE_NOT_REGISTERED, UNEXPECTED_ERROR, CANCEL_REQUESTED, BLOCKED_BUDGET,
    CAPABILITY_BLOCKED, UNKNOWN_JOB, JOB_NOT_RESUMABLE,
)

ALL_CODES: tuple[str, ...] = BUSINESS_CODES + INTERNAL_CODES

# ── 可重试 / 瞬时（网络式）──────────────────────────────────────────────
# 瞬时：允许"同阶段重试 + 指数退避"（网络抖动、限流、下载断线）
TRANSIENT_CODES: frozenset[str] = frozenset({
    NETWORK_TRANSIENT, RATE_LIMIT, DOWNLOAD_FAILED,
})
# 可重试：重试在语义上安全（不会重复扣费/写坏数据）；未必需要退避
RETRYABLE_CODES: frozenset[str] = frozenset({
    NETWORK_TRANSIENT, RATE_LIMIT, DOWNLOAD_FAILED,
    GENERATION_FAILED, GENERATION_TIMEOUT, STAGE_TIMEOUT, UNEXPECTED_ERROR,
    ASR_MISMATCH, SUBTITLE_ALIGN_FAIL,
})
# 业务错误：绝不允许当网络抖动无限重试
PERMANENT_CODES: frozenset[str] = frozenset(set(BUSINESS_CODES) - set(RETRYABLE_CODES))

# ── RepairEngine 白名单动作（Phase 4 必做任务 9）─────────────────────────
RETRY_SAME = "RETRY_SAME"              # 同 workflow、同 prompt 再跑一次
SWITCH_WORKFLOW = "SWITCH_WORKFLOW"    # 换兼容 workflow 链
COMPRESS_PROMPT = "COMPRESS_PROMPT"    # 压缩 prompt 后再提交
REGENERATE_SHOT = "REGENERATE_SHOT"    # 重出成片（画面/人物/产品不合格）
REBUILD_SUBTITLE = "REBUILD_SUBTITLE"  # 只重建字幕/对齐，不重新生成
WAIT_AND_RESUME = "WAIT_AND_RESUME"    # 等窗口/配额，不当作生成失败
REQUIRE_HUMAN = "REQUIRE_HUMAN"        # 交人工（凭据/合规/资产缺失）
ABORT = "ABORT"                        # 停止（无修复动作）

REPAIR_ACTIONS: tuple[str, ...] = (
    RETRY_SAME, SWITCH_WORKFLOW, COMPRESS_PROMPT, REGENERATE_SHOT,
    REBUILD_SUBTITLE, WAIT_AND_RESUME, REQUIRE_HUMAN, ABORT,
)
# 允许在同一个 stage 内自动重跑的动作（其余动作会改变 job 走向）
IN_STAGE_ACTIONS: frozenset[str] = frozenset({
    RETRY_SAME, SWITCH_WORKFLOW, COMPRESS_PROMPT, REGENERATE_SHOT, REBUILD_SUBTITLE,
})

REPAIR_MAP: dict[str, str] = {
    NETWORK_TRANSIENT: RETRY_SAME,
    RATE_LIMIT: RETRY_SAME,
    DOWNLOAD_FAILED: RETRY_SAME,
    GENERATION_FAILED: RETRY_SAME,
    GENERATION_TIMEOUT: SWITCH_WORKFLOW,
    PROVIDER_REJECTED: SWITCH_WORKFLOW,
    PROMPT_TOO_LONG: COMPRESS_PROMPT,
    VISUAL_QA_FAIL: REGENERATE_SHOT,
    PRODUCT_DEFORMED: REGENERATE_SHOT,
    WRONG_SPEAKER: REGENERATE_SHOT,
    HUMAN_ANATOMY_FAIL: REGENERATE_SHOT,
    QA_FAILED: REGENERATE_SHOT,
    ASR_MISMATCH: REBUILD_SUBTITLE,
    SUBTITLE_ALIGN_FAIL: REBUILD_SUBTITLE,
    PUBLISH_QUOTA: WAIT_AND_RESUME,
    COMPLIANCE_BLOCK: REQUIRE_HUMAN,
    AUTH_EXPIRED: REQUIRE_HUMAN,
    PUBLISH_AUTH: REQUIRE_HUMAN,
    CONFIG_MISSING: REQUIRE_HUMAN,
    ASSET_MISSING: REQUIRE_HUMAN,
    NO_SPEC: REQUIRE_HUMAN,
    PLAN_FAILED: REQUIRE_HUMAN,
    PROMPT_NOT_COMPILED: REQUIRE_HUMAN,
    PROMPT_BUDGET_EXCEEDED: COMPRESS_PROMPT,
    WORKFLOW_INCOMPATIBLE: REQUIRE_HUMAN,
    PRESCREEN_REQUIRED: REQUIRE_HUMAN,
    PRESCREEN_FAILED: REQUIRE_HUMAN,
    CLAIM_UNMAPPED: REQUIRE_HUMAN,
    CLAIM_NEEDS_VERIFICATION: REQUIRE_HUMAN,
    CLAIM_FORBIDDEN: REQUIRE_HUMAN,
    MISSING_INPUT: REQUIRE_HUMAN,
    CAPABILITY_BLOCKED: REQUIRE_HUMAN,
    BLOCKED_BUDGET: REQUIRE_HUMAN,
    UNKNOWN: ABORT,
}

# ── 人工干预提示（Phase 12：BLOCKED 必须说明"为什么需要人工"）──────────────
# 前端只读这张表，绝不解析中文 message 猜原因（文案一改，提示就哑）。
HUMAN_HINTS: dict[str, str] = {
    CONFIG_MISSING: "缺少必需的配置项：请在设置里补齐后重试。",
    AUTH_EXPIRED: "平台登录已失效：请重新扫码登录该平台；系统已暂停该平台，不会反复重试。",
    PUBLISH_AUTH: "发布凭据无效：请重新登录对应平台后再发布。",
    NETWORK_TRANSIENT: "网络抖动：稍后重试即可（会自动退避，不需要人工处理）。",
    RATE_LIMIT: "触发平台/供应商限流：等窗口过去后再重试。",
    PROMPT_TOO_LONG: "提示词超长：需要压缩提示词或拆分镜头后重试。",
    ASSET_MISSING: "缺少素材（角色/产品/字体/参考图）：请补齐资产后重试。",
    PROVIDER_REJECTED: "生成供应商拒绝了本次请求：请人工检查提示词/内容合规后重试。",
    GENERATION_FAILED: "生成失败：可重试；连续失败请检查供应商额度与模型可用性。",
    GENERATION_TIMEOUT: "生成超时：可换工作流或稍后重试。",
    DOWNLOAD_FAILED: "产物下载失败：检查网络/磁盘后重试。",
    ASR_MISMATCH: "字幕与语音不一致：需要重建字幕或重出镜头。",
    SUBTITLE_ALIGN_FAIL: "字幕对齐失败：需要重建字幕。",
    VISUAL_QA_FAIL: "画面质检不合格：需要按要求重出成片。",
    PRODUCT_DEFORMED: "产品外形被 AI 画坏：必须重出该镜头（不能直接发布）。",
    WRONG_SPEAKER: "说话人不对：必须重出该镜头。",
    HUMAN_ANATOMY_FAIL: "人物肢体异常：必须重出该镜头。",
    COMPLIANCE_BLOCK: "合规拦截：文案触碰红线，需人工改写后再走一遍 Gate。",
    PUBLISH_QUOTA: "发布配额用尽：等下一个发布窗口自动续发，不需要人工。",
    PACKAGING_INCOMPLETE: "发布物料不完整：需人工补齐标题/描述/话题等字段。",
    AI_DISCLOSURE_UNCONFIRMED: "AI 生成声明无法确认：只能走草稿或人工发布，禁止直发。",
    REQUIRE_HUMAN_PUBLISH: "该平台没有草稿通道：只能由人工确认发布。",
    PLATFORM_PAUSED: "平台已被熔断暂停：请先处理账号/凭据问题再解除暂停。",
    NOT_READY: "任务还没到 READY：等成片归档、物料齐备后再发布。",
    ENGAGE_CIRCUIT_OPEN: "自动互动已熔断：请人工检查近期回复后复位。",
    NO_SPEC: "没有可执行的 StorySpec：需要先完成创意规划。",
    PLAN_FAILED: "自主规划失败：请人工确认目标后重新规划。",
    PROMPT_NOT_COMPILED: "提示词还没编译：需要先跑编译阶段。",
    PROMPT_BUDGET_EXCEEDED: "提示词预算超限：需要压缩或减少镜头。",
    WORKFLOW_INCOMPATIBLE: "没有工作流能保住全部关键能力：需要人工调整工作流/镜头。",
    PRESCREEN_REQUIRED: "高风险新构图必须先过 5 秒预筛：需要先跑预筛。",
    PRESCREEN_FAILED: "预筛未通过：不允许直接跑 15 秒正式片，需要人工确认。",
    CLAIM_UNMAPPED: "文案出现未登记的产品承诺：需登记为 claim 或改写文案。",
    CLAIM_NEEDS_VERIFICATION: "文案命中待核验口径：需人工核对来源后放行。",
    CLAIM_FORBIDDEN: "文案命中禁用改写/绝对化/价格红线：必须改写。",
    MISSING_INPUT: "缺少必需输入：请补齐后重试。",
    PREFLIGHT_FAILED: "分镜预检未过：需要修正分镜再提交。",
    QA_FAILED: "质检未通过：需要按要求修复或重出。",
    COMPOSE_FAILED: "后期合成失败：检查素材/字体/音频后重试。",
    PACKAGE_FAILED: "打包物料失败：需要人工检查后重跑打包。",
    STAGE_TIMEOUT: "阶段超时：可重试（可能是供应商慢）。",
    STAGE_NOT_REGISTERED: "该阶段没有注册实现：需要人工检查部署。",
    UNEXPECTED_ERROR: "未预期错误：请人工查看日志后再决定是否重试。",
    BLOCKED_BUDGET: "成本超过单次上限：需要人工确认预算后再继续（不会自动花钱）。",
    CAPABILITY_BLOCKED: "环境能力缺失（模型/工具/凭据）：请按体检结果补齐能力。",
    CANCEL_REQUESTED: "任务已被人工取消。",
    UNKNOWN_JOB: "任务不存在：请刷新任务台。",
    JOB_NOT_RESUMABLE: "该状态不支持恢复：只能取消或重试。",
    ORCHESTRATOR_ERROR: "编排层错误：请人工查看日志。",
    STAGE_FAILED: "阶段执行失败：可重试；请查看错误码对应处理方式。",
}


def human_action_hint(error_code: str | None, message: str = "") -> str:
    '''error_code 映射到人工提示；表外按动作兜底，绝不编造。'''
    code = str(error_code or UNKNOWN)
    hint = HUMAN_HINTS.get(code)
    if hint:
        return hint
    action = repair_action_for(code)
    fallback = {
        WAIT_AND_RESUME: "属于可等待类问题：等窗口过去后系统会自动续跑，不需要人工。",
        REQUIRE_HUMAN: "需要人工介入：请检查该错误的上下文后手动处理。",
        ABORT: "该错误没有自动修复动作：请人工检查后再决定是否重试。",
    }
    tail = fallback.get(action, "请人工查看任务事件后再决定。")
    return f"{tail}（错误码 {code}）" if not message else f"{tail}（错误码 {code}：{message[:120]}）"


# 白名单动作 → 终止/暂停语义
ACTION_STATE: dict[str, str | None] = {
    WAIT_AND_RESUME: "PAUSED",
    REQUIRE_HUMAN: "BLOCKED",
    ABORT: "FAILED",
}


def repair_action_for(error_code: str | None) -> str:
    """error_code → 白名单动作（表外一律 ABORT，绝不猜）。"""
    return REPAIR_MAP.get(error_code or UNKNOWN, ABORT)


def is_transient(error_code: str | None) -> bool:
    return (error_code or "") in TRANSIENT_CODES


def is_retryable(error_code: str | None) -> bool:
    return (error_code or "") in RETRYABLE_CODES


def backoff_delay(attempt: int, *, base: float = 2.0, cap: float = 60.0) -> float:
    """指数退避（第 N 次失败后等多久）；仅在瞬时错误上使用。"""
    return float(min(cap, base * (2 ** max(0, int(attempt) - 1))))


# ── 异常 ───────────────────────────────────────────────────────────────
class OrchestratorError(Exception):
    """所有编排层异常的基类。"""

    error_code = ORCHESTRATOR_ERROR
    retryable = False

    def __init__(self, message: str = "", *, error_code: str | None = None,
                 data: dict | None = None, next_action: str = "stop") -> None:
        super().__init__(message or self.error_code)
        if error_code:
            self.error_code = error_code
        self.message = message or self.error_code
        self.data = dict(data or {})
        self.next_action = next_action

    def to_dict(self) -> dict:
        return {"error_code": self.error_code, "message": self.message,
                "next_action": self.next_action, "retryable": self.retryable,
                "data": self.data}


class UnknownJob(OrchestratorError):
    error_code = UNKNOWN_JOB


class JobNotResumable(OrchestratorError):
    error_code = JOB_NOT_RESUMABLE


class StageFailure(OrchestratorError):
    """单个 stage 执行失败（可重试性由具体 error_code 决定）。"""

    error_code = STAGE_FAILED
    retryable = True


class CapabilityBlocked(OrchestratorError):
    """环境能力缺失（模型/工具/凭据），不是代码问题。"""

    error_code = CAPABILITY_BLOCKED


class BudgetExceeded(OrchestratorError):
    error_code = BLOCKED_BUDGET


class Cancelled(OrchestratorError):
    error_code = CANCEL_REQUESTED


class ProviderError(OrchestratorError):
    """供应商调用失败（提交/轮询/下载）；子类各自带 taxonomy error_code。"""

    error_code = UNKNOWN


class ConfigMissing(ProviderError):
    error_code = CONFIG_MISSING


class AuthExpired(ProviderError):
    error_code = AUTH_EXPIRED


class NetworkTransient(ProviderError):
    error_code = NETWORK_TRANSIENT
    retryable = True


class RateLimited(ProviderError):
    error_code = RATE_LIMIT
    retryable = True


class PromptTooLong(ProviderError):
    error_code = PROMPT_TOO_LONG


class AssetMissing(ProviderError):
    error_code = ASSET_MISSING


class ProviderRejected(ProviderError):
    error_code = PROVIDER_REJECTED


class GenerationFailed(ProviderError):
    error_code = GENERATION_FAILED
    retryable = True


class GenerationTimeout(ProviderError):
    error_code = GENERATION_TIMEOUT
    retryable = True


class DownloadFailed(ProviderError):
    error_code = DOWNLOAD_FAILED
    retryable = True


# message 模式 → error_code（供应商把原因写在文案里，但接口没有稳定错误码）
_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (DOWNLOAD_FAILED, ("下载失败", "download failed", ".part")),
    (PROMPT_TOO_LONG, ("最大长度", "too long", "超过最大", "prompt 的长度", "max length")),
    (AUTH_EXPIRED, ("401", "403", "unauthorized", "invalid token", "鉴权失败",
                    "token 过期", "apikey 未配置", "api_key 未配置", "未配置")),
    (RATE_LIMIT, ("429", "rate limit", "too many requests", "限流", "频率限制")),
    (CONFIG_MISSING, ("未配置", "missing config", "not configured")),
    (NETWORK_TRANSIENT, ("connect", "timeout", "timed out", "10053", "10054",
                         "网络", "连接错误", "connection reset", "sslerror")),
    (PROVIDER_REJECTED, ("提交失败", "reject", "invalid", "参数", "400", "不支持")),
)


def classify_exception(exc: BaseException | str) -> str:
    """把任意供应商异常/消息归一到 taxonomy error_code（不认识 → UNKNOWN）。"""
    if isinstance(exc, OrchestratorError):
        return exc.error_code
    text = str(exc).lower()
    for code, needles in _PATTERNS:
        if any(n.lower() in text for n in needles):
            return code
    return UNKNOWN
