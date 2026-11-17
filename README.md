# God of an AI Society

Current release: **v0.2.0**. This version includes the shared agent harness, English model inputs, After the Bounty player mode, personality experiments, and the [proposed core simulation plan](docs/core-simulation-plan.md).

**God of an AI Society** is a game about playing god over a society of autonomous AI residents. The current command-line prototype lets you watch how residents cooperate and pass on knowledge. In [The Relay Archive](scenarios/archive.md), residents start with equal abilities. Each turn they can experiment, use someone else's method, publish a discovery, or teach a peer. The simulation records who actually uses each piece of knowledge. In the Water Station scenario, you can also intervene by sending a private oracle message.

Run the scripted demo with `python -X utf8 play.py` using Python 3.10 or later. See [the local model setup](#让本地模型决策) for the Water Station test commands. The UTF-8 flag keeps the Chinese console output readable on Windows.

[Agent harness and decision logs](docs/agents.md) explains what each resident sees, how the model submits an action, and how to trace the result.

Development has started on the shared [character data contract](docs/character-data.md). Use `python -X utf8 -m society --template adaptive_keeper --resident-id ari` to inspect an example resident.

## 焚船之后

12 名居民在岛上争用船具房、学习与传授技艺，并在 1808 年决定是否接触外船。规则和历史背景见[场景设计](scenarios/after_the_bounty/design.md)。启动本地 Ollama 后，在项目根目录运行以下命令。默认使用 `phi4-mini:3.8b`。

```powershell
# 玩家模式。选开局目标、影响卡和干预时机
python -X utf8 -m scenarios.after_the_bounty --play --seed 17 --log after_the_bounty_play17.json

# 只跑 1790 年
python -X utf8 -m scenarios.after_the_bounty --rounds 1 --seed 17 --log after_the_bounty_round1.json

# 推进 18 个年度回合，再进入 1808 年迎船终章
python -X utf8 -m scenarios.after_the_bounty --seed 17 --log after_the_bounty_seed17.json
```

玩家模式用数字选菜单。开局把一张影响卡交给一名居民。每局有两次干预机会，可以召开公开议事或推迟一次已预警的风暴。结局可以保存一张有事件证据的遗产卡，下局开场就能把它交给另一名居民。默认遗产文件为 `after_the_bounty_legacy.json`，可用 `--legacy-file` 指定另一份。

可用 `--personality sol=organizer` 给索尔指定性格模板。预设有 `mediator`（调停者）、`keeper`（重诺者）和 `organizer`（组织者）。用以下命令在同一局面逐项比较低、中、高性格值的实际动作。

```powershell
python -X utf8 -m scenarios.after_the_bounty.personality_benchmark --log after_the_bounty_personality_benchmark.json
```

日志每年保存一次，包含英文状态卡、居民决策、结算事件和用时。`health_readback` 记录模型对自身健康状态的复述，`health_rejections` 记录被健康检查拒绝的输出。风暴预警时，状态卡会显示实际避风准备、公开的保护承诺和尚无人认领的居民。对照测试时为每次运行设置不同的 `--log` 路径。可用 `--model` 换本地模型，或用 `--delay-storm 1797` 将第一次风暴推迟一年。

## 12 人狼人杀

预女猎白首日情景。运行一晚及白天的竞选、发言和放逐，输出可复盘的全知日志。参见 [规则与运行说明](scenarios/werewolf.md)。

```powershell
python -X utf8 -m scenarios.werewolf --seed 17 --log werewolf_day1.json
```

## 接力档案馆

居民独立试验、共享修复方法，并在第 7 轮迎来新成员。模型读取英文状态卡，日志保存每次方法交接与采用。完整规则见 `scenarios/archive.md`。

```powershell
python -X utf8 -m scenarios.archive --residents 20 --rounds 12 --seed 17 --log archive_20_12_rounds.json
```

## 同起点聚落

情景说明与实现位于 `scenarios/commons.md` 和 `scenarios/commons.py`。运行时，本地模型以英文读取规则、角色状态卡和可选动作，也以英文输出公告与理由。终端运行提示使用中文。

```powershell
python -X utf8 -m scenarios.commons --residents 20 --rounds 1 --log commons_20_english.json
```

## 断水站

「断水站」是一个八人、四轮的 Python 原型。稳压和校准完成后，有人得在停机前重启设备。居民可以交接记录、作出承诺、承担维修费用，或用手上的装置独立撤离。终端会显示工程进度、角色处境和带编号的关键事件。

## 运行演示

需要 Python 3.10 或更新版本，无需安装 Python 软件包。

```powershell
python -X utf8 play.py
python -X utf8 play.py --route withdraw --verbose
python -X utf8 play.py --route shutdown
python -X utf8 play.py --private-archive
```

这些演示展示协作、独立撤离后由别人补位，以及停机受困。脚本用来检验规则。相同开局下模型会作出什么选择，要用本地推理实测。

## 让本地模型决策

打开 [Ollama for Windows](https://ollama.com/download/windows)。使用便携版且模型已存放在 D 盘时，在第一个 PowerShell 窗口启动服务，并保持窗口打开。

```powershell
$env:OLLAMA_MODELS = 'D:\AI-Society\ollama-models'
$env:OLLAMA_HOST = '127.0.0.1:11434'
& 'D:\AI-Society\ollama\ollama.exe' serve
```

新开一个 PowerShell 窗口，进入项目根目录。先确认服务可连接且已识别模型。

```powershell
(Invoke-RestMethod 'http://127.0.0.1:11434/api/tags').models.name
```

如果列表里缺少 `phi4-mini:3.8b`，用 `ollama pull phi4-mini:3.8b` 下载。便携版可将这条命令里的 `ollama` 换成 `& 'D:\AI-Society\ollama\ollama.exe'`。

### 只跑第一轮

```powershell
python -X utf8 play.py --backend ollama --rounds 1 --seed 17 --log station_round1.json
```

### 跑完整一局

```powershell
python -X utf8 play.py --backend ollama --seed 17 --log station_full.json
```

两个命令都会在项目根目录保存 JSON 日志。加 `--interactive` 可在每轮开始前暂停并发送神谕，加 `--verbose` 可在终端显示完整事件。

八个角色在快速模式下默认共享一份本地 [Phi-4 Mini 3.8B](https://ollama.com/library/phi4-mini:3.8b)。`--think` 默认使用 `gemma4:12b`，可以用 `--model` 指定其他模型。每次推理只使用一个角色的英文状态卡和合法动作。状态卡写明剩余轮次、公开分工、维修进度和动作后果。玩家每轮都可以观察结果，全局可以用英文对一人发一次私密神谕。日志记录各轮用时、输入和输出 token、无效输出与重试次数。

可用 `--model qwen3.5:9b-q4_K_M` 跑 Qwen 对照，或用 `python -X utf8 evaluate.py --out runs.json` 重跑三局实验。后者记录每次决策看到的状态卡。

要试玩知识交接，建议用 `python -X utf8 play.py --backend ollama --fallback-calibration-cost 3 --interactive --verbose`。这会把没有 R1 时的校准成本从 2 点提高到 3 点。加上 `--private-archive` 可观察记录只能交给一个人时的结果。

首轮对照可以使用同一模型与采样种子，多次切换 `--lin-broke-past-promise`，看岑是否改变交接对象或保住退路。也可通过 `--private-archive` 或 `--extra-budget 2` 改变实验条件。用 `--think` 对照深度思考。模型遇到无效输出会重试一次，再等待一轮。服务不可用时，程序停止并给出错误。

## 一轮如何进行

1. 处理玩家的神谕。引擎冻结本轮所有角色的状态卡与合法动作。
2. 按顺序逐个请求角色选择。所有请求结束后，引擎才应用选定动作。
3. 施工须在轮初具备前置条件。多人抢修同一步时，起始优先位置每轮轮换。第一个完成的人支付算力，其余人保留算力。无效动作视为等待。
4. 消息、记录和施工成果在下一轮可用。承诺的传递与履行分别记账。手握撤离装置的角色如果花到不足两点，就会失去独立撤离选项。耗尽算力的角色先完成动作，之后留站等待救援。

以后接并行推理时，可以沿用轮初状态卡和确定性的结算规则。终端摘要由规则筛选事件。完整日志是供玩家查看的全知视角，角色按自己的可见范围接收事件。

## 测试

```powershell
python -m unittest -v
```
