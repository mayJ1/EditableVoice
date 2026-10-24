# EditableVoice

**把口播配音做成可修改、可回退的工程。改一句，只重做受影响的片段。**

EditableVoice 是面向 AI Agent 的本地口播制作 Skill。它使用本人或获授权的参考声音生成配音，将稿件、分段音频、生成参数和历史版本组织成可继续编辑的工程。

当前版本：**v0.1.0 · 技术预览版**。重点解决「配音生成以后不好改」，不承诺消除 AI 味或实现任意情绪表演。

## 为什么做这个项目

录口播时，一句话反复读错、面对麦克风不自然，常常会让创作者不停删除重录。声音克隆能减轻一部分录音压力，但生成结果仍可能出现断词、停顿和语气问题；如果每改一句都要重新生成整段，修改本身又成了负担。

EditableVoice 尝试把这件事拆开：先试听小样，再逐段生成；满意的片段留下，不满意的片段重做；停顿在拼接层调整，历史版本随时回退。

底层语音能力来自 [OmniVoice](https://github.com/k2-fsa/OmniVoice)，使用体验受到 [VoiceStudio](https://github.com/debpalash/VoiceStudio) 启发。**本项目的贡献是可编辑口播流程、缓存、版本管理与导出，不是新的声音模型。**

## 能做什么

| 能力 | v0.1 的行为 |
| --- | --- |
| 声音档案 | 导入授权参考录音与准确转录，在多个工程中复用 |
| 保留原稿 | 保存原始稿件，配音标注和朗读替代文字独立管理 |
| 小样试听 | 先生成指定片段，确认后继续全文 |
| 局部修改 | 按编号修改文字、语速或重新生成，不重复合成未改变的有效片段 |
| 停顿调整 | 修改段与段之间额外插入的静音，无需模型重新生成 |
| 版本回退 | 保留历史 take，恢复对应文字与合成参数 |
| 增量缓存 | 根据文字、声音、模型、参数和环境识别可复用音频 |
| 剪辑交付 | 导出完整 WAV、编号分段 WAV、稿件和段级时间清单 |

### 目前不包含

- 任意情绪标签控制，以及「完全听不出 AI」的保证。
- 逐字无缝修补；局部修改以语义片段为单位。
- 词级字幕对齐、自动剪视频或保持原剪辑时间轴不变。
- 自动改写锁定的稿件、自动联网转录、训练或微调新声音模型。
- 云端配音 API、网页控制台、一键全平台安装器。

## 使用流程

```text
建立授权声音档案 → 提交稿件 → 确认分段和方案 → 试听小样
→ 生成全文 → 指定片段修改 / 回退 → 导出剪辑素材
```

与 Agent 对话时，可以这样表达需求：

> 用我本人的声音生成这篇口播。正文已经锁稿，不要改文字；先给我两句小样。

> 第二句读得不自然，重新生成，其他已经满意的录音保留。

> 第一句后面多停半秒，不用重新生成声音。

> 还是用第二句的上一个版本，然后导出完整音频和分段素材。

这些是由 Agent 理解的自然语言请求，不是脚本自身的聊天接口。Agent 应先阅读 [SKILL.md](SKILL.md)，再调用脚本执行。

## 在 Agent 中使用

本仓库根目录就是 Skill 包，入口为 `SKILL.md`，Skill 名为 **`editable-voiceover`**。

```bash
git clone https://github.com/mayJ1/EditableVoice.git
```

可以把仓库内容放到所用 Agent 支持的 Skill 目录中，并将目录命名为 `editable-voiceover`；具体发现、安装或重新加载方式以该 Agent 的文档为准。也可以先让 Agent 直接阅读克隆目录中的 `SKILL.md`。

可交给 Agent 的部署请求：

> 请阅读 EditableVoice 仓库中的 SKILL.md，检查本机环境，在独立目录准备运行环境。下载模型或安装较大依赖之前，先告诉我需要的空间和位置。不要修改我现有的 VoiceStudio，不要上传我的声音资料。

**兼容条件：**Agent 能读取 Skill、执行本地 Python 脚本并访问用户授权的文件。仅有聊天能力、不能执行脚本的客户端不能直接运行本项目。面向不同 Agent 复用同一套核心脚本，不代表已在所有 Agent 上完成端到端验证。

## 运行环境

### 轻量功能与真实合成是两层依赖

- 工程管理、16-bit PCM WAV 拼接和基础测试：Python **3.10+** 标准库。
- 真实语音合成：OmniVoice、PyTorch、torchaudio、soundfile 及其依赖；需要完整本地模型。
- 24-bit 等参考音频的副本转换：需要 soundfile。

建议使用独立虚拟环境。Windows 示例：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
```

macOS / Linux 示例：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
```

然后使用该虚拟环境的 Python：

1. 按 [PyTorch 官方说明](https://pytorch.org/get-started/locally/) 安装匹配系统、显卡和驱动的 PyTorch / torchaudio，不要盲目复制其他机器的 CUDA 安装命令。
2. 按 [OmniVoice 上游安装说明](https://github.com/k2-fsa/OmniVoice#installation) 安装模型运行库。常规包安装入口为 `python -m pip install omnivoice soundfile`，这里的 `python` 必须指向刚创建的环境。
3. 在获得用户确认后，下载 [OmniVoice 完整模型快照](https://huggingface.co/k2-fsa/OmniVoice) 至仓库以外的目录，包含权重、文本分词器与 `audio_tokenizer`；不能只复制单个权重文件。
4. 运行环境检查，再做短音频合成与人工试听。部署时记录实际安装版本；本版尚未提供独立环境的锁定依赖清单。

本仓库不包含模型，也不自动下载模型。**推理进程设置离线模式，仅从指定本地模型目录加载。**首次安装依赖和下载模型仍需要联网，这不等于推理需要联网。

> 本机验证使用 Windows、RTX 3060 8GB 以及已有 VoiceStudio 的 Python 环境。未启动桌面 UI，但尚未完成干净机器部署测试。CPU、其他显卡和系统的可用性、速度不能由该次测试推定。

更多说明见 [运行环境与模型](references/runtime.md)。

## 命令行快速上手

下面在仓库根目录执行；`python` 代表已准备好的推理环境解释器。所有示例路径都应替换为你自己的路径。建议将声音和工程保存在仓库之外。

### 1. 检查环境

```bash
python scripts/voiceover.py doctor
python scripts/voiceover.py doctor --model "../voice-data/models/OmniVoice" --probe-runtime
```

`doctor` 不安装依赖或下载模型。模型文件检查通过不代表已通过实际推理；`--probe-runtime` 会导入运行库，但不加载权重。

### 2. 建立声音档案

准备本人或已获授权的清晰录音与逐字转录文件。建议参考录音 5–15 秒，本版接受 2–20 秒；超过范围时请同时调整录音和对应文字，避免错配。

```bash
python scripts/voiceover.py voice --directory "../voice-data/voices/mine" --audio "../voice-data/reference.wav" --transcript "../voice-data/reference.txt" --name "我的口播声音" --consent
```

`--consent` 表示调用者已确认授权，不会替代真实授权。原录音不会被覆盖；非16-bit参考音频会在声音目录保存转换副本。基础质量检查不等于能自动判断噪声、本人身份或转录正确性。

### 3. 创建工程并查看分段

```bash
python scripts/voiceover.py init --project "../voice-data/projects/demo" --script "../voice-data/script.txt" --voice "../voice-data/voices/mine" --model "../voice-data/models/OmniVoice"
python scripts/voiceover.py show --project "../voice-data/projects/demo"
```

原稿另存为 `source.txt`，不会因后续编辑而改写。当前合成适配器使用中文语言设置，非中文口播不在本版验收范围。

### 4. 先生成小样，再生成全文

```bash
python scripts/voiceover.py render --project "../voice-data/projects/demo" --only 001,002 --approved
python scripts/voiceover.py export --project "../voice-data/projects/demo" --only 001,002
```

确认试听方向后：

```bash
python scripts/voiceover.py render --project "../voice-data/projects/demo" --approved
python scripts/voiceover.py export --project "../voice-data/projects/demo"
```

`--approved` 记录用户已同意本次方案，不表示省略用户确认。续生成会复用未过期、未损坏的小样片段。

### 5. 修改一句，或重新演绎一句

替换第二段文字后只生成该段：

```bash
python scripts/voiceover.py edit --project "../voice-data/projects/demo" --segment 002 --text "这是修改后的第二句话。"
python scripts/voiceover.py render --project "../voice-data/projects/demo" --only 002 --approved
```

文字不变，生成一个新版本：

```bash
python scripts/voiceover.py render --project "../voice-data/projects/demo" --only 002 --retake --approved
```

这会更换随机种子，不保证新版本一定更自然，应试听后选择。

### 6. 调停顿与回退

```bash
python scripts/voiceover.py edit --project "../voice-data/projects/demo" --segment 001 --pause-ms 700
python scripts/voiceover.py show --project "../voice-data/projects/demo"
python scripts/voiceover.py rollback --project "../voice-data/projects/demo" --segment 002 --take "替换为show返回的历史take_id"
python scripts/voiceover.py export --project "../voice-data/projects/demo"
```

`pause_ms` 是段后**额外插入**的静音，不包含模型原音频已有的静音。尾段不再额外添加。回退恢复历史正文、朗读替代文字、语速和种子，保留当前停顿。换了全局声音或模型后，旧音频可能不再匹配当前配置；导出会拒绝过期片段。

完整命令见 [命令与工程格式](references/commands.md)。

## 输出与工程结构

```text
demo/
├── source.txt                 原始稿件
├── manifest.json              当前分段、设置、take与历史记录
├── revisions/                 修改前的工程快照
├── audio/                     各段历史音频
└── exports/
    └── 时间戳-随机后缀/
        ├── full.wav           本次完整音频
        ├── segments/          本次采用的编号分段WAV
        ├── script.txt         本次导出的正文
        └── timeline.json      段级起止时间与朗读替代文字
```

每次导出建立新目录，不覆盖旧成品。`timeline.json` 是段级边界，**不是精确字幕**。修改一句后，其时长和后续位置可能变化。

声音目录与工程目录是私人数据，不要提交到 GitHub。换电脑时需主动迁移它们，并用 `configure` 更新路径；只复制 Skill 不会自动拥有你的声音。

## 测试与验证状态

```bash
python scripts/test_voiceover.py
```

测试使用合成测试音，不是用户声音。基础测试仅使用标准库；未安装 numpy / soundfile 时，相关可选适配测试会跳过。真实声音测试必须另外进行。

截至 v0.1 的本机验证：

- 22 项自动化测试全部通过，包含局部更新、缓存、停顿、回退、失败恢复、文件损坏与路径限制等。
- 使用已授权本人参考录音，完成三句中文配音及第二句替换。
- 修改第二句后，第一、三句文件 SHA256 保持不变。
- 增加450ms拼接静音，输出总时长准确增加450ms，未调用模型。
- 回退并恢复停顿后，完整 WAV 与初版逐字节一致。

尚未完成：干净机器独立部署、其他 Agent 端到端实测、跨平台实机测试、全面的主观听感评测。**工程测试通过不等于声音质量已达真人水平。**

## 隐私、授权与发布

- 仅处理本人或明确获授权的声音，不用于冒充、诈骗或误导性身份呈现。
- 参考录音和转录保存在用户指定的本地声音目录。本项目不提供云端上传接口，也不包含遥测逻辑；外部 Agent 的数据处理方式需另行了解。
- 不要在公开 Issue、截图或日志中暴露录音、转录、账户路径或私人工程。
- 仓库忽略常见录音、模型、密钥和工程文件，但 `.gitignore` 不是隐私扫描器；提交前仍需检查。
- 发布 AI 配音内容时，遵守目标平台的标识与内容规则。

## 来源与许可状态

- [OmniVoice](https://github.com/k2-fsa/OmniVoice)：底层声音模型及推理接口。
- [OmniVoice 模型卡](https://huggingface.co/k2-fsa/OmniVoice)：具体权重和依赖信息。
- [VoiceStudio](https://github.com/debpalash/VoiceStudio)：原始使用场景与工作流启发。

本仓库不分发 VoiceStudio 实现、模型权重、音频编码器或用户录音。第三方代码、权重、参考声音和生成内容的使用条件应分别核对。

**本仓库原创代码的开源许可证尚未指定**；公开可见不等于授予任意复制、修改、再分发或商用许可。正式许可证将在作者确认后补充，第三方许可也不因此改变。
