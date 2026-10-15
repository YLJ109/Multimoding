"""OpenAI-compatible provider presets used by the settings page."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CloudProviderPreset:
    """Connection defaults and declared modalities for one cloud provider."""

    key: str
    name: str
    llm_base_url: str = ""
    llm_model: str = ""
    asr_base_url: str = ""
    asr_model: str = ""
    tts_base_url: str = ""
    tts_model: str = ""
    tts_voice: str = ""
    capabilities: str = ""
    note: str = ""


PROVIDER_PRESETS: tuple[CloudProviderPreset, ...] = (
    CloudProviderPreset(
        key="custom",
        name="自定义 OpenAI-compatible",
        capabilities="按接口实际能力填写",
        note="Base URL、模型和能力都保留手动编辑。",
    ),
    CloudProviderPreset(
        key="openai",
        name="OpenAI",
        llm_base_url="https://api.openai.com/v1",
        llm_model="gpt-4o-mini",
        asr_base_url="https://api.openai.com/v1",
        asr_model="whisper-1",
        tts_base_url="https://api.openai.com/v1",
        tts_model="gpt-4o-mini-tts",
        tts_voice="alloy",
        capabilities="文本 / 图像理解 / 语音识别 / 语音合成",
        note="使用同一个 API Key 时，语音服务会自动复用语言模型密钥。",
    ),
    CloudProviderPreset(
        key="deepseek",
        name="DeepSeek 深度求索",
        llm_base_url="https://api.deepseek.com/v1",
        llm_model="deepseek-chat",
        capabilities="文本 / 推理",
        note="DeepSeek 当前预设不声明图像和语音端点，语音提醒会保留本地方案。",
    ),
    CloudProviderPreset(
        key="qwen",
        name="阿里云百炼 / 通义千问",
        llm_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        llm_model="qwen-plus",
        asr_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        asr_model="qwen3-asr-flash",
        tts_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        tts_model="qwen-tts",
        tts_voice="Cherry",
        capabilities="文本 / 图像理解 / 语音识别 / 语音合成",
        note="默认模型均为可编辑项；图像理解可在模型框换成对应 Qwen-VL 模型。",
    ),
    CloudProviderPreset(
        key="kimi",
        name="Kimi / Moonshot",
        llm_base_url="https://api.moonshot.cn/v1",
        llm_model="kimi-latest",
        capabilities="文本 / 长上下文 / 图像理解",
        note="视觉能力取决于所选 Kimi 模型；没有兼容语音端点时使用本地语音。",
    ),
    CloudProviderPreset(
        key="zhipu",
        name="智谱 GLM",
        llm_base_url="https://open.bigmodel.cn/api/paas/v4",
        llm_model="glm-4-flash",
        capabilities="文本 / 图像理解",
        note="视觉任务可将模型切换为 GLM 视觉系列。语音端点由智谱独立 API 提供。",
    ),
    CloudProviderPreset(
        key="siliconflow",
        name="SiliconFlow 硅基流动",
        llm_base_url="https://api.siliconflow.cn/v1",
        llm_model="Qwen/Qwen3-8B",
        asr_base_url="https://api.siliconflow.cn/v1",
        asr_model="FunAudioLLM/SenseVoiceSmall",
        tts_base_url="https://api.siliconflow.cn/v1",
        tts_model="FunAudioLLM/CosyVoice2-0.5B",
        tts_voice="default",
        capabilities="文本 / 图像理解 / 语音识别 / 语音合成",
        note="适合比赛现场用一个密钥快速验证多模态链路。",
    ),
    CloudProviderPreset(
        key="minimax",
        name="MiniMax 稀宇科技",
        llm_base_url="https://api.minimax.chat/v1",
        llm_model="MiniMax-Text-01",
        capabilities="文本 / 图像理解 / 独立语音平台",
        note="语音接口若不在 OpenAI-compatible 路径下，请切回本地 TTS 或自定义端点。",
    ),
    CloudProviderPreset(
        key="hunyuan",
        name="腾讯混元",
        llm_base_url="https://api.hunyuan.cloud.tencent.com/v1",
        llm_model="hunyuan-turbos-latest",
        capabilities="文本 / 图像理解",
        note="需要账号已开通混元 OpenAI-compatible 服务。",
    ),
    CloudProviderPreset(
        key="spark",
        name="讯飞星火",
        llm_base_url="https://spark-api-open.xf-yun.com/v1",
        llm_model="4.0Ultra",
        capabilities="文本 / 图像理解",
        note="不同星火版本通常在模型名中区分，模型框可直接修改。",
    ),
    CloudProviderPreset(
        key="qianfan",
        name="百度千帆 / 文心",
        llm_base_url="https://qianfan.baidubce.com/v2",
        llm_model="ernie-4.0-8k",
        capabilities="文本 / 图像理解",
        note="千帆兼容接口可能要求账号先创建应用或访问凭证。",
    ),
    CloudProviderPreset(
        key="yi",
        name="零一万物 Yi",
        llm_base_url="https://api.lingyiwanwu.com/v1",
        llm_model="yi-lightning",
        capabilities="文本 / 部分视觉模型",
        note="视觉能力取决于所选用模型。",
    ),
    CloudProviderPreset(
        key="baichuan",
        name="百川智能",
        llm_base_url="https://api.baichuan-ai.com/v1",
        llm_model="Baichuan4",
        capabilities="文本 / 图像理解",
        note="模型名和可用能力以当前账号控制台为准。",
    ),
    CloudProviderPreset(
        key="mimo",
        name="Xiaomi MiMo（OpenRouter）",
        llm_base_url="https://openrouter.ai/api/v1",
        llm_model="xiaomi/mimo-7b-rl",
        capabilities="文本 / 推理",
        note="MiMo 通过 OpenRouter 路由；也可以改成自建或第三方 OpenAI-compatible 地址。",
    ),
    CloudProviderPreset(
        key="openrouter",
        name="OpenRouter 聚合平台",
        llm_base_url="https://openrouter.ai/api/v1",
        llm_model="openrouter/auto",
        capabilities="取决于所选上游模型",
        note="模型框填写 OpenRouter model id；平台可路由多种国内外模型。",
    ),
)


def provider_preset(key: str) -> CloudProviderPreset:
    """Return one preset and fall back to custom for unknown persisted values."""
    normalized = str(key or "").strip().lower()
    return next(
        (preset for preset in PROVIDER_PRESETS if preset.key == normalized),
        PROVIDER_PRESETS[0],
    )


def default_provider_for_session(environment: Mapping[str, str]) -> CloudProviderPreset:
    """Select a first-run provider without persisting any environment secret."""
    if str(environment.get("DASHSCOPE_API_KEY", "")).strip():
        return provider_preset("qwen")
    return provider_preset("custom")
