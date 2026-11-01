# JSS 论文数据与 RQ1–RQ4 代码

本包按作者指定范围整理，只含四部分。不包含模型输出、人工标注材料、主实验逐发布指标表、论文排版/绘图脚本或单独的表格生成模块。代码包含 RQ 分析，以及新增的模型调用和输出解析。

## 目录

```text
data/
  raw/                         原始采集的四个文件（不合并、不去重）
    releases_01.jsonl           118,093 条发布采集记录
    releases_02.jsonl           2,399 条发布采集记录
    pull_requests_01.jsonl      1,817,356 条 PR 采集记录
    pull_requests_02.jsonl      39,633 条 PR 采集记录
    manifest.json              来源、数量、哈希与脱敏计数
  used/
    main_cohort.csv             最终 1,418 个发布／154 个仓库名单
    longitudinal_metrics.csv    原始 780 条纵向指标／12 个仓库
code/
  common.py                    共享读取及样本完整性检查
  rq1.py                       总体质量
  rq2.py                       分组比较
  rq3.py                       按变更类型分析覆盖和遗漏
  rq4.py                       纵向趋势、阶段差值和 bootstrap
  run_llm.py  两阶段通用模型调用及在线解析
  parse_model_outputs.py        已有原始响应的离线 JSON 解析
prompts/
  stage1.py                    Stage 1 系统及用户提示词构造函数
  stage1_system.txt            可直接阅读的系统提示词
  stage2.py                    统一英文 Stage 2 提示词构造函数
  stage2_system.txt            可直接阅读的系统提示词
  schemas/                    两阶段输出结构
requirements.txt
```

## 原始数据及版本

四个 JSONL 文件保留每条原始记录及原顺序，只有敏感文本会被替换为 `[REDACTED]`。`01/02` 仅用于避免同名文件覆盖，不设置主采集/补采子目录；具体原始相对路径见 manifest。原始来源文件从未被改写。

原始记录包含重复采集和后续未纳入论文的项目，不能把原始文件行数作为论文样本数。论文整理阶段为 243 个仓库、54,215 条发布记录，进一步筛选后的主实验名单为 1,418 个发布、154 个仓库。RQ4 是独立的 780 条记录、12 个仓库，不能替换为后续的 680 条清洗版本。

`main_cohort.csv` 对应当前主实验最终共同样本；`longitudinal_metrics.csv` 保留原有指标数值、零值、序号及批次。两份 CSV 不做重新估计或去重。

## 运行

在 Python 3.11 环境中，从包根目录执行：

```shell
python -m pip install -r requirements.txt
python code/rq4.py
```

RQ4 默认采用原始发布序号、Mann–Kendall 趋势检验、首尾各 floor(N/3) 条的阶段差，以及 10,000 次 Accuracy 循环块 bootstrap（块长 2/3/4，主分析为 3）。结果输出到标准输出，不生成论文格式的表格或图片。保留原报告先四位再最终舍入的数值链条。

RQ1–RQ3 只公开必要的分析代码；按指定范围，不提供其模型判断和最终指标输入。运行时需自行提供对应输入，不能只凭样本名单复现数值：

```shell
python code/rq1.py --metrics /path/to/final_release_metrics.csv
python code/rq2.py --metrics /path/to/final_release_metrics.csv
python code/rq3.py --model DS --judgments /path/to/final_ds_judgments.jsonl
python code/rq3.py --model QW --judgments /path/to/final_qw_judgments.jsonl
```

RQ1/2 的 CSV 需要 `model`（DS/QW）、`sample_id` 和 `code/common.py` 列出的 11 项指标；每模型覆盖全部 1,418 个最终发布。分组元数据以包内名单为准。未定义指标为空值，按指标分别排除。RQ3 输入为最终修正后的判断 JSONL（支持含 `parsed_output` 的外层结构），依据 `fact_alignments` 中的相关性、覆盖标签、类型及属性计算；不把非标准标签静默归为遗漏。`test_only` 和 `other` 仍参与风险比的其余类别分母。

## 提示词

按作者指定，主实验公开包统一提供英文 Stage 2 版本，不包含 RQ4 提示词。`.py` 文件只含构造函数，不含调用密钥、网络调用器或个人配置。Stage 1/2 的 `build_system_prompt()` 和 `build_user_prompt()` 返回相应文本；Stage 2 用户输入需要 `reference_change_points`。模板参数结构与函数中的字段访问一致。

公开的提示词是作者指定的当前统一版本，不将其表述为已逐次核实的全部历史 API 请求快照。重新调用模型的结果可能不同于原实验。

## 模型调用与解析

`code/run_llm.py` 来源于项目已有同名调用脚本，保留模型消息构造、HTTP 请求、JSON 提取、并发、重试、批次标识及断点续跑逻辑。公开版改为仅从环境变量读取密钥，兼容包内 schema 路径，并拒绝损坏的 JSONL 和非对象 JSON 响应；重试错误与保存的响应中会遮盖当前 API 密钥。运行摘要补充温度、最大输出长度和 thinking 参数。它是经过这些明确调整的公开版本，不是历史文件的逐字副本。

先在本机安全设置 `DEEPSEEK_API_KEY` 或自选的密钥环境变量，不要把实际值写入脚本、命令示例或仓库。准备请求 JSONL，每行至少包含：

```json
{"sample_id":"EXAMPLE_001","system_prompt":"...","user_prompt":"...","schema_path":"prompts/schemas/release_change_reference_schema.json"}
```

两阶段分别使用 `prompts/stage1.py`、`prompts/stage2.py` 的构造函数准备请求。Stage 2 将 schema 改为 `release_note_judgment_schema.json`。实际请求内容需要自行准备，本包没有提供完整的请求构建与证据采集流程。

```shell
python code/run_llm.py --requests-path requests_stage1.jsonl --output-dir runs/stage1 --model deepseek-chat --api-key-env DEEPSEEK_API_KEY --run-batch-id example_stage1 --temperature 0.1
python code/run_llm.py --requests-path requests_stage2.jsonl --output-dir runs/stage2 --model deepseek-chat --api-key-env DEEPSEEK_API_KEY --run-batch-id example_stage2 --temperature 0.1
```

Qwen 等兼容接口可用 `--api-url`、`--model`、`--api-key-env` 指定实际服务、模型及环境变量；需要关闭 thinking 时使用 `--disable-thinking`。`--resume` 跳过当前批次已经完成的样本，`--max-concurrency` 控制并发。真实执行会调用付费服务。

输出为 `raw_responses.jsonl`、`parsed_outputs.jsonl`、`status.jsonl` 和 `run_summary.json`。解析器支持纯 JSON 对象、JSON 代码块及附带说明文字的对象。schema 是加入提示词的约束，原调用器不实施 JSON Schema 的程序级字段校验，不能把“解析成功”理解为“语义与 schema 已验证”。

离线重新解析已有原始响应，无须模型或密钥：

```shell
python code/parse_model_outputs.py --raw runs/stage1/raw_responses.jsonl --output runs/stage1/reparsed_outputs.jsonl
```

离线解析保留成功记录的元数据和顺序，不自动去重；报告失败数量，有失败时返回非零退出码。不会覆盖已有输出。输出日志可能包含研究输入和模型文本，不应未经检查直接上传。

## 复现边界

- 原始纵向指标表有跨批次、重复发布身份等历史问题；按作者要求保留论文的 780 条分析记录，不以去重结果替换。
- 该原始表缺乏可用发布日期，所以包内数据可复现 RQ4 趋势、阶段差和 bootstrap，不能独立复现 2024–2025 年度比较。`rq4.py` 可以对外部提供的、经核实且保持原指标的带日期数据运行年度比较。
- 本包不提供人工验证材料，也不提供主实验模型输出。因此不是包含所有输入的端到端复现包。
- 原始爬取中的 commit SHA 和变更数量不等于完整 commit 正文或 patch；仅包含原文件实际保存的信息。

## 隐私与来源权利

原始 JSONL 已扫描常见密钥、Bearer token、凭据赋值、私钥块及 Windows 用户目录标识，匹配内容已遮盖；报告只记录数量，不记录秘密值。公开仓库名、公开贡献者账号和来源链接保留。自动扫描无法保证覆盖所有未知凭据格式。

未包含 `.env`、个人配置、运行日志、绝对源盘路径、API 密钥或密码配置。第三方 GitHub 内容仍受其原有权利约束，本包没有为第三方内容另行指定统一许可证。
