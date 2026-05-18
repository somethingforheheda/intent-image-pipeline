# Troubleshooting

## Missing API Key

Create a dedicated image-generation config file or set a dedicated image-generation environment variable. Do not use the user's general `OPENAI_API_KEY`; that may be reserved for Codex/chat access.

macOS/Linux:

```bash
mkdir -p ~/.config/qijixing-image
cat > ~/.config/qijixing-image/config.json
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\qijixing-image"
notepad "$env:APPDATA\qijixing-image\config.json"
```

Config shape:

```json
{
  "api_key": "sk-...",
  "base_url": "https://api.qijixing.fun/v1"
}
```

Optional environment variables:

- `QIJIXING_IMAGE_CONFIG`: custom config file path
- `QIJIXING_IMAGE_API_KEY`: dedicated image-generation API key
- `QIJIXING_IMAGE_BASE_URL`: optional API base URL override

If the config file does not exist, tell the user the exact path to create. If the user sends a key in chat and asks Codex to set it up, write it to the dedicated config file immediately, then say: "这个 key 已经在对话里暴露过，建议你重新生成一个专门用于生图的 key，再替换配置文件里的值。"

## HTTP 401

The key is missing, invalid, expired, or not accepted by the selected base URL. Confirm the resolved config path and environment variables.

User-facing explanation: "生图专用密钥可能没配置好或已经失效。请检查专用配置文件里的 api_key，或配置 QIJIXING_IMAGE_API_KEY。不要直接复用 Codex 对话用的 OPENAI_API_KEY。"

Stop rule: Do not generate replacement images with local filters or other tools. Wait for the user to configure the key or approve a clearly described fallback.

## HTTP 429

The service is rate-limiting requests. Increase `request_interval`, reduce batch size, or retry later.

User-facing explanation: "接口现在请求太频繁了。可以把请求间隔调大，或者稍后直接重跑同一个任务。已经生成的图片不会重复生成。"

Stop rule: Do not switch to a different generation method unless the user approves it after hearing that the original AI workflow is blocked.

## HTTP 5xx or Timeouts

Increase `request_timeout`, keep `max_rounds` enabled, and rerun the same job. Existing outputs are skipped.

User-facing explanation: "上游服务临时失败或响应太慢。通常不是图片或提示词的问题，建议调大超时时间后重跑。"

Stop rule: Keep the AI job intact. Rerun or tune timeout/retry settings; do not create non-AI substitutes.

## No Images Found

The runner supports `.png`, `.jpg`, `.jpeg`, and `.webp`. Set `recursive` to `true` if images are nested in subfolders.

User-facing explanation: "输入文件夹里没有找到支持的图片。确认图片是不是 png/jpg/jpeg/webp，或者图片是不是放在子文件夹里。"

## Output Count Is Short

Re-run the same command. The runner scans missing files and retries only unfinished tasks.

User-facing explanation: "有些图没生成成功，可以直接重跑同一个任务。脚本会自动跳过已经生成的，只补缺失的。"

## How Codex Should Report Failures

Do not tell beginner users to open the log themselves. Read `run.log`, look for `failure_summary`, `[diagnosis]`, HTTP status codes, and the final missing-output list. Then report:

- What completed successfully
- What failed
- The most likely cause
- The next action to try
- Whether rerunning the same job is safe

Use this pattern when the API cannot run:

```text
这次没有生成 AI 图片，因为 <原因>。
我没有改用本地滤镜或其他方式生成，避免产出不符合你的要求。
下一步：<配置 key / 稍后重试 / 调大超时 / 检查网络>。
修好后可以继续跑同一个 job，已经生成的文件会自动跳过。
```

Never present non-AI filtered images as generated results for an AI image workflow.
