"""第三方响应契约（Phase 13）—— 字段变化必须"立刻报警"，而不是等主链崩在第 N 步。

设计约定：
  · 契约只声明**主链真正读取**的字段，多出来的字段一律允许（provider 加字段不该让生产崩）；
  · 生产代码在解析响应后立即 `assert_contract(...)`，把模糊的 KeyError 换成点名到字段的错误；
  · `tests/fixtures/contracts/` 里每个 provider 至少一份真实形状的样本，测试全量校验
    （样本被改坏就会红），`broken/` 子目录放反例并断言必须被拒绝。

用法：
    from lib.contracts import assert_contract, validate
    assert_contract("autodl_submit", body)
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_MISSING = object()


class ContractError(RuntimeError):
    """第三方响应不符合契约（字段缺失 / 类型变化 / 取值越界）。"""

    def __init__(self, name: str, problems: list[str]) -> None:
        self.name = name
        self.problems = list(problems)
        super().__init__("响应不符合契约 " + name + "：" + "，".join(self.problems))


@dataclass(frozen=True)
class Rule:
    """一条字段约束。path 支持 `a.b` 与 `a[].b`（数组逐项）。

    `when=(path, allowed)` 表示只有该条件字段落在 allowed 里时才校验本规则
    （用于"任务成功时才必须有 results"这类条件契约）。
    """

    path: str
    types: tuple[type, ...] = ()
    required: bool = True
    enum: tuple[Any, ...] | None = None
    nonempty: bool = False
    when: tuple[str, tuple[Any, ...]] | None = None
    note: str = ""


@dataclass(frozen=True)
class Contract:
    """一个 provider 端点的响应契约。"""

    name: str
    endpoint: str
    consumer: str
    rules: tuple[Rule, ...] = ()
    custom: Callable[[Any], list[str]] | None = None


def _fmt_types(types: tuple[type, ...]) -> str:
    return "/".join(t.__name__ for t in types)


def _walk(node: Any, parts: list[str]):
    """按路径产出值，缺失产出 `_MISSING`。`a[]` 表示对数组每个元素继续下钻。"""
    if not parts:
        yield node
        return
    head, rest = parts[0], parts[1:]
    if head.endswith("[]"):
        key = head[:-2]
        if not isinstance(node, dict) or key not in node:
            return
        seq = node[key]
        if not isinstance(seq, list):
            yield _MISSING
            return
        for item in seq:
            yield from _walk(item, rest)
        return
    if not isinstance(node, dict) or head not in node:
        yield _MISSING
        return
    yield from _walk(node[head], rest)


def _probe(payload: Any, path: str) -> Any:
    got = list(_walk(payload, path.split(".")))
    if not got:
        return _MISSING
    return got[0]


def _check_rule(payload: Any, rule: Rule) -> list[str]:
    if rule.when is not None:
        cond_path, allowed = rule.when
        cond = _probe(payload, cond_path)
        if cond is _MISSING or cond not in allowed:
            return []
    where = rule.path
    if rule.note:
        where = rule.path + "（" + rule.note + "）"
    values = list(_walk(payload, rule.path.split(".")))
    if not values or all(v is _MISSING for v in values):
        return ["缺少字段 " + where] if rule.required else []
    problems: list[str] = []
    for value in values:
        if value is _MISSING:
            problems.append(where + " 的数组元素不完整")
            continue
        if rule.types:
            ok = isinstance(value, rule.types) and not (isinstance(value, bool) and bool not in rule.types)
            if not ok:
                problems.append(where + " 类型应为 " + _fmt_types(rule.types)
                                + "，实际 " + type(value).__name__)
                continue
        if rule.enum is not None and value not in rule.enum:
            problems.append(where + " 取值 " + repr(value) + " 不在 " + repr(rule.enum))
            continue
        if rule.nonempty and value == "":
            problems.append(where + " 不能是空字符串")
    return problems


def _check_uploadpost_status(body: Any) -> list[str]:
    """Upload-Post 的状态响应：`results` 或 `platforms` 是"平台 -> 对象"的字典。"""
    if not isinstance(body, dict):
        return ["响应不是 JSON 对象"]
    table = body.get("results")
    if table is None:
        table = body.get("platforms")
    if table is None:
        if isinstance(body.get("status"), str):
            return []
        return ["既没有 results / platforms，也没有顶层 status"]
    if not isinstance(table, dict):
        return ["results / platforms 应为对象，实际 " + type(table).__name__]
    problems: list[str] = []
    for key, value in table.items():
        if not isinstance(value, dict):
            problems.append("results[" + str(key) + "] 应为对象，实际 " + type(value).__name__)
        elif "status" in value and not isinstance(value["status"], str):
            problems.append("results[" + str(key) + "].status 应为字符串，实际 "
                            + type(value["status"]).__name__)
    return problems


def _check_uploadpost_me(body: Any) -> list[str]:
    """Upload-Post 的 /me：envelope 必须是对象，账号字段存在时必须是字符串。"""
    if not isinstance(body, dict):
        return ["响应不是 JSON 对象"]
    problems: list[str] = []
    for key in ("profile", "username", "email", "user"):
        if key in body and body[key] is not None and not isinstance(body[key], str):
            problems.append(key + " 应为字符串，实际 " + type(body[key]).__name__)
    return problems


# ── PostFlow CLI 契约（本地可执行文件，不走 HTTP） ──────────────────────
#
# 通道：`postflow.exe <platform> upload-video --account .. --video .. --title ..
#        --desc .. --tags ..`，判定看 returncode + stdout/stderr 文本。
POSTFLOW_SUBCOMMAND = "upload-video"
POSTFLOW_REQUIRED_FLAGS: tuple[str, ...] = (
    "--account", "--video", "--title", "--desc", "--tags",
)
# 凭据失效信号：出现这些词就判 AUTH_EXPIRED（而不是普通失败），交给人工重新登录。
POSTFLOW_AUTH_MARKERS: tuple[str, ...] = (
    "登录", "扫码", "未登录", "认证失效", "token expired", "unauthorized",
    "401", "auth", "credential", "cookie",
)


# 平台风控 / 验证码 / 账号异常信号：出现这些词说明**平台在质疑这个账号**，
# 不是"发失败了重试一次"的场景。计划 §15.6：一律 REQUIRE_HUMAN —— 暂停该平台 + 交人工，
# 绝不自动重试、绝不变换路径绕过。
POSTFLOW_HUMAN_MARKERS: tuple[str, ...] = (
    "验证码", "风控", "账号异常", "异常操作", "操作频繁", "频繁操作", "环境异常",
    "captcha", "risk control", "unusual activity", "account suspended",
    "suspicious activity", "human verification",
)


def postflow_needs_human(text: str) -> bool:
    """平台风控/验证码/账号异常信号（大小写不敏感）→ 必须转人工。"""
    low = (text or "").lower()
    return any(marker.lower() in low for marker in POSTFLOW_HUMAN_MARKERS)


# ── 契约表 ────────────────────────────────────────────────────────────

CONTRACTS: dict[str, Contract] = {}


def _register(contract: Contract) -> Contract:
    CONTRACTS[contract.name] = contract
    return contract


_register(Contract(
    name="deepseek_chat",
    endpoint="POST {llm.base_url}/chat/completions",
    consumer="lib/llm.chat",
    rules=(
        Rule("choices", (list,), note="OpenAI 兼容候选列表"),
        Rule("choices[].message.content", (str,),
             note="正文，思考模型可能返回空串，由上层翻倍重试而不是当契约破坏"),
    ),
))

_register(Contract(
    name="autodl_submit",
    endpoint="POST /api/v1/comfyui/comfyui_workflow/{workflow_id}",
    consumer="s4_generate.autodl_client.create_task",
    rules=(
        Rule("code", (str,), enum=("Success",)),
        Rule("data.task_id", (str,), nonempty=True, note="付费任务 id"),
    ),
))

_register(Contract(
    name="autodl_result",
    endpoint="GET /api/v1/comfyui/comfyui_workflow/result/{task_id}",
    consumer="s4_generate.autodl_client.query_task / poll_task",
    rules=(
        Rule("code", (str,), enum=("Success",)),
        Rule("data", (dict,)),
        Rule("data.status", (str,), required=False),
        Rule("data.results", (list,), required=False),
        Rule("data.results[].type", (str,), when=("data.status", ("SUCCESS",))),
        Rule("data.results[].url", (str,), nonempty=True, when=("data.status", ("SUCCESS",))),
    ),
))

_register(Contract(
    name="uploadpost_upload",
    endpoint="POST /api/upload",
    consumer="s6_publish.uploadpost.upload_video",
    rules=(
        Rule("request_id", (str,), nonempty=True, note="轮询状态用的上传请求 id"),
    ),
))

_register(Contract(
    name="uploadpost_status",
    endpoint="GET /api/uploadposts/status?request_id=",
    consumer="s6_publish.uploadpost.upload_status / wait_upload",
    custom=_check_uploadpost_status,
))

_register(Contract(
    name="uploadpost_me",
    endpoint="GET /api/uploadposts/me",
    consumer="s6_publish.uploadpost.whoami",
    custom=_check_uploadpost_me,
))


def names() -> tuple[str, ...]:
    """全部已登记契约名（测试用它遍历 fixtures 目录）。"""
    return tuple(sorted(CONTRACTS))


def validate(name: str, payload: Any) -> list[str]:
    """校验一份响应，返回问题列表（空列表 = 合规）。未知契约名直接抛错。"""
    contract = CONTRACTS.get(name)
    if contract is None:
        raise ContractError(name, ["未登记的契约名：" + str(name)])
    problems: list[str] = []
    for rule in contract.rules:
        problems.extend(_check_rule(payload, rule))
    if contract.custom is not None:
        problems.extend(contract.custom(payload))
    return problems


def is_valid(name: str, payload: Any) -> bool:
    return not validate(name, payload)


def assert_contract(name: str, payload: Any) -> Any:
    """生产解析路径上的契约闸门：不合契约立刻抛 ContractError（点名到字段）。"""
    problems = validate(name, payload)
    if problems:
        raise ContractError(name, problems)
    return payload


def postflow_is_auth_error(text: str) -> bool:
    """PostFlow CLI 输出里是否出现凭据失效信号（大小写不敏感）。"""
    low = (text or "").lower()
    return any(marker.lower() in low for marker in POSTFLOW_AUTH_MARKERS)


def postflow_command_flags(cmd: list[str]) -> list[str]:
    """从一条 PostFlow 命令里抽出 flag（契约测试断言必需参数一个不少）。"""
    return [token for token in cmd[2:] if token.startswith("--")]
