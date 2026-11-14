# God of an AI Society

**God of an AI Society** is a game about playing god over a society of autonomous AI residents. The current command-line prototype lets you watch how residents cooperate and pass on knowledge. In [The Relay Archive](scenarios/archive.md), residents start with equal abilities. Each turn they can experiment, use someone else's method, publish a discovery, or teach a peer. The simulation records who actually uses each piece of knowledge. In the Water Station scenario, you can also intervene by sending a private oracle message.

Run the scripted demo with `python -X utf8 play.py` using Python 3.10 or later. To run the agents locally, start Ollama, run `ollama pull gemma4:12b`, and use the scenario command below. The UTF-8 flag keeps the Chinese console output readable on Windows.

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

打开 [Ollama for Windows](https://ollama.com/download/windows) 并保持它运行，在终端执行：

```powershell
ollama pull gemma4:12b
python -X utf8 play.py --backend ollama --interactive --log run.json
```

只推进一轮可使用 `python -X utf8 play.py --backend ollama --rounds 1 --verbose`。

八个角色默认共享一份本地 [Gemma 4 12B](https://ollama.com/library/gemma4:12b)。每次推理只使用一个角色的状态卡和合法动作。状态卡写明剩余轮次、公开分工、维修进度和动作后果。玩家每轮都可以观察结果，全局可以对一人发一次私密神谕。日志记录各轮用时、输入和输出 token、无效输出与重试次数。

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
