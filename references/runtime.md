# 运行环境与分发

工程管理、WAV拼接和测试只需要 Python 3.10+ 标准库。真实合成需要另装 OmniVoice、匹配硬件的 PyTorch/torchaudio、soundfile 及其依赖。使用独立虚拟环境，不改全局 Python 或 VoiceStudio 环境。

先运行 `python scripts/voiceover.py doctor`。doctor 不加载模型，不联网、不安装。检查 CUDA 运行情况可加 `--probe-runtime`（会导入 torch，不加载模型）。

在用户指定的运行环境目录执行 `python -m venv .venv`，后续用该目录内 Python 的绝对路径安装和调用。Windows 为 `.venv/Scripts/python.exe`，macOS/Linux 为 `.venv/bin/python`。先按 https://pytorch.org/get-started/locally/ 安装匹配硬件的 torch/torchaudio，再 `python -m pip install omnivoice soundfile`。安装前告知所需网络、磁盘和下载位置并获得同意。上游当前指南：https://github.com/k2-fsa/OmniVoice#installation 。首次安装版本需记录 `pip freeze`；跨平台不承诺全部经过实机验证。

## 模型

本版只接受本地模型目录。获得用户确认后从 https://huggingface.co/k2-fsa/OmniVoice 下载完整快照，包含权重、文本分词器和 `audio_tokenizer`；不能只拿 model.safetensors。不要读取或输出 Hugging Face token。下载属于部署动作，脚本不会自动执行。

有 VoiceStudio 缓存时先 `doctor --model <快照目录>`；完整性检查通过不代表模型已能成功推理。可在隔离进程复用已有可用 Python 做兼容验证，但发布包不能依赖用户机器硬编码路径或复制 VoiceStudio 的修改版实现。

## 本人声音

参考音频建议用 PCM WAV，先准备 5–15 秒清晰正常表达的录音，必须有准确转录。本版允许 2–20 秒，超限不自动截断，避免音频与转录错配。16-bit PCM WAV 直接复制；24-bit 等格式需要 soundfile，自动在声音档案内另存单声道16-bit副本，不改原音频。质量检查只报告时长、采样率、声道、峰值、RMS、近削波比例，不宣称自动证明无噪声或转录正确。

克隆只读用户指定且已授权的音频，复制到声音目录。不训练新权重；档案内音频与转录可跨工程重用。私人资料不要放到可分享 Skill 包内。传给引擎的是参考音频和人工确认的转录，不自动联网转写。

## 实现来源与边界

本 skill 的工程管理与拼接脚本独立编写；不复制 VoiceStudio 代码，不把其应用许可证推断为模型许可证。

- OmniVoice 上游及 Python API：https://github.com/k2-fsa/OmniVoice （仓库标示 Apache-2.0；发布时仍检查具体版本许可）
- 权重及模型卡：https://huggingface.co/k2-fsa/OmniVoice
- VoiceStudio（作为原始使用场景与备用工具）：https://github.com/debpalash/VoiceStudio

OmniVoice、依赖音频编码器、参考声音和生成内容可能有不同许可或使用条件；公共发布/商用前分别核对。无克隆他人声音的默认授权。
