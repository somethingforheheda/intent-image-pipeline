# 故障排查

## 缺少 API 密钥

创建专用生图配置文件或设置专用生图环境变量。不得使用用户的通用 `OPENAI_API_KEY`，那个可能是 Codex/对话专用的。

macOS/Linux：

```bash
mkdir -p ~/.config/qijixing-image
cat > ~/.config/qijixing-image/config.json
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\qijixing-image"
notepad "$env:APPDATA\qijixing-image\config.json"
```

配置格式：

```json
{
  "api_key": "sk-...",
  "base_url": "https://api.qijixing.fun/v1"
}
```

可选环境变量：

- `QIJIXING_IMAGE_CONFIG`：自定义配置文件路径
- `QIJIXING_IMAGE_API_KEY`：专用生图 API 密钥
- `QIJIXING_IMAGE_BASE_URL`：可选的 API base URL 覆盖

配置文件不存在时，告知用户应创建的确切路径。如果用户在对话中发送密钥并要求配置，立即写入专用配置文件，然后说：「这个 key 已经在对话里暴露过，建议你重新生成一个专门用于生图的 key，再替换配置文件里的值。」

## HTTP 401

密钥缺失、无效、已过期，或不被所选 base URL 接受。确认已解析的配置路径和环境变量。

用户提示：「生图专用密钥可能没配置好或已经失效。请检查专用配置文件里的 api_key，或配置 QIJIXING_IMAGE_API_KEY。不要直接复用 Codex 对话用的 OPENAI_API_KEY。」

停止规则：不得用本地滤镜或其他工具生成替代图片。等待用户配置好密钥，或用户在了解情况后批准明确描述的降级方案。

## HTTP 429

服务正在限流。增大 `request_interval`，减小批量大小，或稍后重试。

用户提示：「接口现在请求太频繁了。可以把请求间隔调大，或者稍后直接重跑同一个任务。已经生成的图片不会重复生成。」

停止规则：除非用户在了解原始 AI 工作流已阻塞后批准，否则不得切换到其他生成方式。

## HTTP 5xx 或超时

增大 `request_timeout`，保持 `max_rounds` 启用，重新跑同一个任务。已有输出会自动跳过。

用户提示：「上游服务临时失败或响应太慢。通常不是图片或提示词的问题，建议调大超时时间后重跑。」

停止规则：保持 AI 任务不变。调整超时/重试配置后重跑，不得创建非 AI 替代品。

## 找不到图片

脚本支持 `.png`、`.jpg`、`.jpeg` 和 `.webp`。如果图片在子文件夹里，将 `recursive` 设为 `true`。

用户提示：「输入文件夹里没有找到支持的图片。确认图片是不是 png/jpg/jpeg/webp，或者图片是不是放在子文件夹里。」

## 输出数量不足

重新跑同一个命令。脚本会扫描缺失文件并只重试未完成的任务。

用户提示：「有些图没生成成功，可以直接重跑同一个任务。脚本会自动跳过已经生成的，只补缺失的。」

## Codex 汇报失败的方式

不要让新手用户自己去打开日志。读取 `run.log`，查找 `failure_summary`、`[diagnosis]`、HTTP 状态码和最终缺失输出列表，然后汇报：

- 哪些成功完成了
- 哪些失败了
- 最可能的原因
- 下一步应该做什么
- 重跑同一个任务是否安全

API 无法运行时使用以下格式：

```text
这次没有生成 AI 图片，因为 <原因>。
我没有改用本地滤镜或其他方式生成，避免产出不符合你的要求。
下一步：<配置 key / 稍后重试 / 调大超时 / 检查网络>。
修好后可以继续跑同一个 job，已经生成的文件会自动跳过。
```

不得将非 AI 滤镜处理的图片作为 AI 图像工作流的生成结果呈现给用户。
