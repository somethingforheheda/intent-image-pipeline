---
name: intent-image-pipeline
description: 自然语言图像生成与编辑工作流自动化。当用户要求创建、编辑、批量生成或转换图片时使用，适用场景包括：产品图、电商主图、场景图、社交封面、头像、背景替换、批量图生图、提示词扩展、可重试生成流水线、图像工作流配置等。
---

# Intent Image Pipeline

## 概述

将用户的自然语言图像意图转换为可运行的生成任务。批量图生图工作优先使用内置的 `scripts/image_pipeline.py`，它负责跨平台配置发现、重试、日志、缺失输出检测和断点续跑。

## 强制停止规则

- `size` 字段的宽和高必须都是 16 的倍数。如果用户指定的分辨率不满足此条件（例如 `1000x1000`、`1920x1080`），不得继续执行——直接告知用户该值无效，并给出最近的合法备选值（例如 `1008x1008`、`1920x1072` 或 `1024x1088`）。不得自行静默修改分辨率。
- 如果 AI 图像 API 因以下原因无法运行：密钥缺失/无效、base URL 不可达、配额/限流、网络故障、超时或上游服务错误，分析日志后停止工作流。
- 不得静默地将 AI 图像生成或编辑任务替换为本地 PIL/OpenCV 滤镜、截图、占位图、模拟输出、非 AI 图像处理或任何近似替代方案。
- 只有在明确告知用户"这不是 AI 生成"并得到用户明确同意后，才可以提供非 AI 降级方案。
- 遇到阻塞时，说明阻塞原因、下一步具体操作，以及同一任务是否可以安全重跑。不得为了"推进进度"而生成替代图片。

## 工作流程

1. 只询问阻塞性细节：输入路径、期望的输出风格/用途、每张源图的输出数量，以及主体是否必须保持不变。用户意图足够清晰时，使用保守的默认值。
2. 需求宽泛或模糊时，读取 `references/workflow-patterns.md` 选择合适的任务形状。
3. 需要特定领域的提示词约束、风格变体或主体保留语言时，读取 `references/prompt-recipes.md`。
4. 在用户的工作文件附近或临时工作目录中创建 job JSON 文件。不得在 job 文件中写入 API 密钥。
5. 首次运行或高风险批量任务，在执行完整任务前先跑冒烟测试：

```bash
python3 /path/to/intent-image-pipeline/scripts/image_pipeline.py --job /path/to/job.json --smoke-test
```

6. 冒烟测试通过后执行完整任务。失败则停止并说明诊断结果，不得切换工具或生成方式。

```bash
python3 /path/to/intent-image-pipeline/scripts/image_pipeline.py --job /path/to/job.json
```

7. 汇报输出目录、目标总数、已完成数量以及任何失败/缺失的任务。
8. 如果脚本失败或输出数量少于预期，自行读取 `run.log` 并将可能原因翻译成用户能理解的语言。不要让新手用户自己去看日志。

## 用户配置

脚本从专用生图配置文件或专用生图环境变量中读取凭据。不得读取或复用通用的 Codex/OpenAI 对话密钥（如 `OPENAI_API_KEY`）。不得将密钥硬编码到 skill、job JSON 或脚本中。

默认配置路径：

- macOS/Linux：`~/.config/qijixing-image/config.json`
- Windows：`%APPDATA%\qijixing-image\config.json`

可选配置路径覆盖：

- `QIJIXING_IMAGE_CONFIG`

支持的配置字段：

```json
{
  "api_key": "sk-...",
  "base_url": "https://api.qijixing.fun/v1",
  "default_model": "gpt-image-2",
  "default_quality": "high",
  "default_format": "png"
}
```

解析优先级：

1. CLI 参数覆盖
2. 专用环境变量：`QIJIXING_IMAGE_API_KEY`、`QIJIXING_IMAGE_BASE_URL`
3. 用户配置文件
4. 默认值（`base_url` 默认为 `https://api.qijixing.fun/v1`）

配置文件不存在时，告知用户应在哪里创建。如果用户在对话中粘贴密钥并要求配置，立即将其写入专用配置文件，然后提醒该密钥已在对话中暴露，建议重新生成并替换配置文件中的值。

## Job JSON 格式

生成任务时使用以下结构：

```json
{
  "input_dir": "/绝对路径/输入图片目录",
  "output_dir": "/绝对路径/输出图片目录",
  "prompts": [
    "Keep the product unchanged. Create a clean bright ecommerce main image."
  ],
  "size": "1024x1024",
  "quality": "high",
  "output_format": "png",
  "model": "gpt-image-2",
  "request_timeout": 300,
  "max_retries": 2,
  "max_rounds": 5,
  "request_interval": 1,
  "recursive": false
}
```

尽量使用绝对路径。`prompts` 可根据用户意图生成，每个输出变体对应一条提示词。

## 输出规则

- 保留原始源文件，不得修改。
- 批量图生图时，输出放在 `output_dir/<源文件名>/prompt_XX.<格式>` 下。
- 脚本跳过已存在的输出文件，支持断点续跑。
- 出现失败时，检查 `run.log`、脚本的 `failure_summary`，并参考 `references/troubleshooting.md` 的常见修复方法。
- 用用户能理解的语言汇报结果，包含最可能的原因和下一步操作。除非原始 API 错误信息有助于用户采取行动，否则不要直接暴露它。
