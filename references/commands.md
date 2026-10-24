# 命令与工程格式

所有命令在 `scripts/voiceover.py`；支持 `--help`。CLI输出JSON，不传入大段音频Base64。

## 声音、工程和配置

- `voice --directory DIR --audio WAV --transcript TXT --name NAME --consent`：新建不可覆盖的授权声音档案，报告基础质量。
- `init --project DIR --script TXT --voice DIR --model MODEL --device auto --seed 42`：原文以 source.txt 保留，建立 manifest.json。只有句末标点或换行分段，空格保留；无句末的超长段由Agent提议人工分段。
- `show --project DIR`：显示文字、朗读替代文字、停顿、当前take和过期状态。
- `configure --project DIR [--voice DIR] [--model DIR] [--device auto|cuda:0|cpu|mps]`：迁移机器或更换模型/声音后配置本地路径；会令不匹配的已有take过期但不会删除。
- `edit --project DIR --segment ID [--text TEXT] [--spoken-text TEXT|--clear-spoken] [--pause-ms 0..10000] [--speed 0.5..2]`：改正文时默认清除旧朗读替代文本，避免仍读旧内容；只改语速不清除。

## 生成与版本

- `render --project DIR [--only 001,002] [--retake] --approved`：只生成未命中有效缓存的指定段。retake产生新随机种子和新take；否则相同请求复用音频。一次进程只加载一次模型。中途失败已成功的段落仍保留，可重试剩余部分。
- `rollback --project DIR --segment ID --take TAKE_ID`：回到历史take并恢复其正文、朗读文字、语速、种子；保留当前停顿。若全局声音/模型已变，回退音频会标为过期，禁止冒充新配置导出。
- `export --project DIR [--only 001,002]`：所有选择段必须有匹配当前配置且未损坏的take。自动建立新的 exports/时间戳-随机目录；输出 full.wav、segments/*.wav、timeline.json、script.txt。小样的时间从0起算。timeline.json提供原文、实际朗读文字和段边界，不是词级字幕。

`pause_ms` 是当前段之后添加的静音，尾段不额外加。它是拼接层能力，不传入模型。修改后重导出即可。内部句间停顿需先在适当语义边界分段，不能把 `[pause]` 等自造标签直接塞进锁稿。

## 数据结构

manifest.json 保存 schema_version、config 和 segments。每段有稳定 id、text、spoken_text、speed、seed、pause_ms、current 和不可覆盖 takes。take记录当前合成输入签名、内容设置、音频SHA256和相对路径。命令修改前将旧manifest备份至 revisions。保留失败产物便于排查，不自动清理用户资料。

缓存检查读取声音文件和模型文件清单；大型权重使用大小/mtime_ns指纹，配置和分词器做内容哈希。不是抗恶意篡改的权重完整性认证。换模型时不要伪造相同mtime/大小；规范部署应固定上游模型快照版本。

同一工程只允许一个写入进程；被中断后残留 .lock 时先确认无活动进程，再人工解除锁，不自动抢占。读取外部工程也需确认可信；脚本限制take路径不逃出工程。工程状态用原子替换写入。
