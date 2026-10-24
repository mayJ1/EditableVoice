---
name: editable-voiceover
description: 用本人或获授权声音制作可编辑口播，支持小样试听、逐段生成、只重做指定句、精确句间停顿和版本回退。适用于文字配音与配音修订，不用于冒充他人，也不自动改写锁稿。
---

# 可编辑口播工作室 v0.1

面向支持本地脚本和文件访问的 Agent。核心命令为 `python <本 skill>/scripts/voiceover.py`，不依赖特定 Agent 或 VoiceStudio 桌面。工程文件与声音资料应在用户工作目录，不要写进可分享的 skill 包。首次部署先读 [运行环境](references/runtime.md)。

## 与用户协作

1. 首次使用确认声音为本人或已经取得许可。用户提供清晰参考 WAV 和逐字转录；先检查质量，不擅自从私人目录挑选身份不明的声音。已有 VoiceStudio 资料可在用户授权后只读导入。
2. 原稿只读。不要润色锁稿；发音修正用 `spoken_text`，并明确它是朗读替代文本。情绪、停顿计划与正文分开。自然语言情绪是创作意图，不表示模型支持；本版不把任意情绪标签传给引擎。
3. 用 `init` 建工程，`show` 展示带编号分段并提出配音安排。自动分段只按句末标点和换行，不切碎长句；分段不合适先调整工程，不直接生成。数字、缩写、专有名词提示用户核听。
4. 默认先 `render --only 001,002` 和 `export --only 001,002` 交小样，等试听同意再生成其余。用户明确要求全文或沿用设置可跳过。所有 render 操作需显式 `--approved`，这是 Agent 记录用户已同意方案，不是用户必须学习的参数。
5. 用户说重做第 N 句，用 `render --only N --retake`；改变文字/语速/参考音先 `edit`。只改停顿用 `edit --pause-ms`，不重合成。试听展示新旧 take 路径。`rollback` 选择旧版本，并恢复其文字、参数。需要连相邻句重做先说明理由。
6. 用 `export` 输出整段 WAV、分段 WAV、时间清单和当前文字。时间清单是段落边界，不是词级字幕。改句后总时长与后续边界可能变化。导出采用新目录，不覆盖旧成品。

## 命令入口

以下路径和参数用实际用户值替换；调用脚本不需要进入 skill 目录。

```text
voiceover.py doctor --model MODEL_DIRECTORY
voiceover.py voice --directory VOICE_DIRECTORY --audio reference.wav --transcript reference.txt --name 我的声音 --consent
voiceover.py init --project PROJECT_DIRECTORY --script script.txt --voice VOICE_DIRECTORY --model MODEL_DIRECTORY
voiceover.py show --project PROJECT_DIRECTORY
voiceover.py edit --project PROJECT_DIRECTORY --segment 002 --pause-ms 500
voiceover.py render --project PROJECT_DIRECTORY --only 001,002 --approved
voiceover.py render --project PROJECT_DIRECTORY --only 002 --retake --approved
voiceover.py edit --project PROJECT_DIRECTORY --segment 002 --text 新正文
voiceover.py edit --project PROJECT_DIRECTORY --segment 002 --spoken-text 仅供发音修正的朗读文字
voiceover.py edit --project PROJECT_DIRECTORY --segment 002 --clear-spoken
voiceover.py rollback --project PROJECT_DIRECTORY --segment 002 --take TAKE_ID
voiceover.py export --project PROJECT_DIRECTORY
```

`--segment 2` 与 `002` 等价。`--only` 接受逗号分隔编号，不接受含糊匹配；先 show 再选。跨项目复用声音用相同声音目录；换电脑须由用户主动迁移声音目录和工程，在 `configure` 更新路径。见 [命令与格式](references/commands.md)。

## 质量和安全边界

- 本版独立 OmniVoice 推理仅从完整的本地模型目录加载，强制离线；不暗中下载，不启用付费服务，不修改 VoiceStudio 数据或全局 Agent 配置。
- 缺模型、依赖或参考转录时停止并解释。不要把调参当作已提升自然度。每段按语义生成；不支持逐字无缝音频修补或任意情绪控制。
- 缓存绑定正文/朗读替代文本、声音录音和转录的内容哈希、推理参数、模型文件指纹与运行环境。停顿不进入语音缓存，重排拼接即可。未改段落的既有音频逐字节保留。
- 不宣称机器测试等于真人声音自然。最终需要用户核听音色、断句、读音、情绪和接缝。参考录音没有隐含训练/微调，克隆档案只是复用参考素材。
- 分发只包含此 skill 的指令、原创脚本与测试；不包含用户录音、模型、工程、日志、测试成品。上游代码/权重/音频编码器许可证分别核对，列明来源。AI配音发布按目标平台要求标识。
