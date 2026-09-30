"""统一强类型配置（Phase 1）—— 全仓唯一配置入口。

设计要点
  1. ROOT 由仓库自身解析，绝不写死盘符；仓库复制到任何目录都能跑。
  2. 权威来源是 `config/default.yaml`；环境变量 `AYHMJ_<SECTION>__<KEY>` 覆盖。
  3. 旧的 `config/pipeline.yaml` 已废弃：存在时只发一条 deprecation 警告，且仅填补
     default.yaml 里没有的键（保证"只有一个权威来源"）。
  4. 所有"本机才存在"的外部依赖（ffmpeg/字体/PostFlow/Python/桌面目录）都走
     `paths.*` + 环境变量 + 自动探测，业务代码不得再写绝对路径。
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG = ROOT / "config" / "default.yaml"
LEGACY_CONFIG = ROOT / "config" / "pipeline.yaml"


class ProductSettings(BaseModel):
    name: str = "轻便侠218电动轮椅"
    brand: str = "爱优护"
    slogan: str = "轻便出行，自由生活"
    keywords: list[str] = Field(default_factory=list)
    assets_dir: str = "assets/products"


class PathSettings(BaseModel):
    state_dir: str = "state"
    out_dir: str = "out"
    logs_dir: str = "logs"
    assets_dir: str = "assets"
    config_dir: str = "config"
    ffmpeg: str = ""
    ffprobe: str = ""
    fonts_dir: str = ""
    python: str = ""
    postflow_dir: str = ""
    desktop_dir: str = ""
    bgm_lib: str = ""
    keyfile: str = ""
    legacy_keyfiles: list[str] = Field(default_factory=list)
    dotenv_files: list[str] = Field(default_factory=list)


class LLMSettings(BaseModel):
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    timeout_seconds: int = 120


class GenerateSettings(BaseModel):
    provider: str = "autodl"
    base_url: str = "https://autodl.art"
    default_workflow: str = "minimax_h3_lightx2v_v5"
    resolution: str = "768p竖"
    duration: int = 15
    quality: str = "standard"
    poll_interval_seconds: int = 20
    max_wait_minutes: int = 25
    prompt_max_chars: int = 10000
    prompt_safe_chars: int = 9800


class AsrSettings(BaseModel):
    backend: str = "faster-whisper"
    model: str = "medium"
    draft_model: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = "zh"


class TrendSettings(BaseModel):
    platforms: list[str] = Field(default_factory=lambda: ["douyin"])
    keywords: list[str] = Field(default_factory=list)
    competitor_accounts: list[str] = Field(default_factory=list)
    pages_per_keyword: int = 3
    min_likes: int = 1000


class SubtitleSettings(BaseModel):
    font: str = "文悦新青年体 (非商用) W8"
    font_size: int = 13
    color: str = "white"
    outline_color: str = "black"
    outline_width: float = 1.0
    bottom_ratio: float = 0.25
    max_chars_per_line: int = 10


class ComposeSettings(BaseModel):
    subtitle: SubtitleSettings = Field(default_factory=SubtitleSettings)
    output: dict[str, Any] = Field(
        default_factory=lambda: {"resolution": "1080x1920", "fps": 30,
                                 "codec": "libx264", "preset": "veryfast", "crf": 23})


class PublishSettings(BaseModel):
    domestic: dict[str, Any] = Field(
        default_factory=lambda: {"enabled": True, "account_name": "ayh-main",
                                 "platforms": ["douyin", "xiaohongshu", "shipinhao"]})
    overseas: dict[str, Any] = Field(
        default_factory=lambda: {"enabled": True, "profile": "xiangge",
                                 "platforms": ["tiktok", "youtube", "instagram",
                                               "facebook", "telegram", "x"]})
    daily_limit: int = 6
    min_interval_minutes: int = 30
    inter_platform_gap_seconds: int = 30
    night_silence: dict[str, str] = Field(
        default_factory=lambda: {"start": "23:00", "end": "07:00"})
    publish_windows: list[dict[str, str]] = Field(
        default_factory=lambda: [{"start": "07:00", "end": "09:00"},
                                 {"start": "12:00", "end": "14:00"},
                                 {"start": "18:00", "end": "22:00"}])
    # ── Phase 10：AI 生成内容声明是发布 Gate 的硬字段 ──────────────
    # 本产线的画面/配音由 AI 生成，默认必须声明；
    # ai_disclosure_confirmable 是"哪个平台的声明能被程序化提交"的**人工确认**结果，
    # 默认空 = 全都没确认 → 该平台只能草稿（无草稿通道则转人工），绝不直发。
    ai_generated: bool = True
    ai_disclosure_confirmable: dict[str, bool] = Field(default_factory=dict)
    # 国内草稿参数（PostFlow CLI）。留空 = 不确认其草稿能力 → 草稿模式直接拒绝执行，
    # 而不是"猜一个参数发出去"。确认后填例如 ["--draft"]。
    domestic_draft_args: list[str] = Field(default_factory=list)


class EngageSettings(BaseModel):
    auto_reply: bool = True
    max_replies_per_hour: int = 20
    reply_cooldown_seconds: int = 60
    escalate_keywords: list[str] = Field(default_factory=list)
    # Phase 10 任务 10：冷却之上再叠一层随机安全间隔；重复回复窗口；连续失败熔断阈值
    reply_jitter_seconds: int = 90
    duplicate_window: int = 50
    circuit_breaker_failures: int = 3


class WebuiSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8899
    debug: bool = False


class Settings(BaseModel):
    product: ProductSettings = Field(default_factory=ProductSettings)
    paths: PathSettings = Field(default_factory=PathSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    generate: GenerateSettings = Field(default_factory=GenerateSettings)
    asr: AsrSettings = Field(default_factory=AsrSettings)
    trend: TrendSettings = Field(default_factory=TrendSettings)
    storyboard: dict[str, Any] = Field(
        default_factory=lambda: {"shots_count": {"min": 4, "max": 6},
                                 "shot_duration": {"min": 2, "max": 5},
                                 "product_shots": 2})
    compose: ComposeSettings = Field(default_factory=ComposeSettings)
    publish: PublishSettings = Field(default_factory=PublishSettings)
    engage: EngageSettings = Field(default_factory=EngageSettings)
    webui: WebuiSettings = Field(default_factory=WebuiSettings)

    # ── 路径解析（全部相对 ROOT，除非已是绝对路径）────────────────
    @property
    def root(self) -> Path:
        return Path(os.environ.get("AYHMJ_ROOT") or ROOT).resolve()

    def resolve(self, value: str) -> Path:
        p = Path(value).expanduser()
        return p if p.is_absolute() else (self.root / p)

    @property
    def state_dir(self) -> Path:
        return self.resolve(self.paths.state_dir)

    @property
    def out_dir(self) -> Path:
        return self.resolve(self.paths.out_dir)

    @property
    def logs_dir(self) -> Path:
        return self.resolve(self.paths.logs_dir)

    @property
    def assets_dir(self) -> Path:
        return self.resolve(self.paths.assets_dir)

    @property
    def config_dir(self) -> Path:
        return self.resolve(self.paths.config_dir)

    @property
    def desktop_dir(self) -> Path:
        if self.paths.desktop_dir:
            return self.resolve(self.paths.desktop_dir)
        return Path.home() / "Desktop" / "ayh-mj"

    @property
    def postflow_dir(self) -> Path:
        return self.resolve(self.paths.postflow_dir or "vendor/postflow")


# ── 环境变量覆盖：AYHMJ_PATHS__FFMPEG=... ──────────────────────
def _env_overrides(prefix: str = "AYHMJ_") -> dict[str, Any]:
    reserved = {"AYHMJ_ROOT", "AYHMJ_CONFIG", "AYHMJ_RUN_LIVE", "AYHMJ_RUN_PAID"}
    tree: dict[str, Any] = {}
    for key, raw in os.environ.items():
        if not key.startswith(prefix) or key in reserved:
            continue
        parts = [p.lower() for p in key[len(prefix):].split("__") if p]
        if len(parts) < 2:
            continue
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):  # 冲突时放弃该键
                break
        else:
            node[parts[-1]] = _coerce(raw)
    return tree


def _coerce(raw: str) -> Any:
    low = raw.strip().lower()
    if low in {"true", "false"}:
        return low == "true"
    if low in {"", "none", "null", "~"}:
        return ""
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


_WARNED = {"legacy_config": False}


def load_settings(config_path: Path | str | None = None) -> Settings:
    """读取权威配置 + 环境覆盖，返回强类型 Settings（每次都新建，便于测试）。"""
    path = Path(config_path or os.environ.get("AYHMJ_CONFIG") or DEFAULT_CONFIG)
    data = _read_yaml(path)

    if path != LEGACY_CONFIG and LEGACY_CONFIG.exists():
        legacy = _read_yaml(LEGACY_CONFIG)
        if legacy:
            if not _WARNED["legacy_config"]:
                _WARNED["legacy_config"] = True
                print(
                    "[deprecated] config/pipeline.yaml 已废弃，请改用 config/default.yaml；"
                    "本次仅用它填补缺失键。", file=sys.stderr)
            data = _deep_merge(legacy, data)  # 权威源优先

    data = _deep_merge(data, _env_overrides())
    return Settings.model_validate(data)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程级缓存（绝大多数调用方用这个）。"""
    return load_settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
