# 论文数据与代码


## 目录

```text
data/
  raw/                         原始文件
    releases_01.jsonl           118,093 条发布记录
    releases_02.jsonl           2,399 条发布记录
    pull_requests_01.jsonl      1,817,356 条 PR 记录
    pull_requests_02.jsonl      39,633 条 PR 记录
    manifest.json             
  used/
    main_cohort.csv             1,418 个发布／154 个仓库
    longitudinal_metrics.csv    780 条指标／12 个仓库
code/
  common.py                    
  rq1.py                       
  rq2.py                       
  rq3.py                       
  rq4.py                      
  run_llm.py 
prompts/
  stage1.py                    
  stage1_system.txt            
  stage2.py                    
  stage2_system.txt           
  schemas/                    
requirements.txt
```

## 运行

在 Python 3.11 环境中，从包根目录执行：

```shell
python -m pip install -r requirements.txt
python code/rq4.py
```


```shell
python code/rq1.py --metrics /path/to/final_release_metrics.csv
python code/rq2.py --metrics /path/to/final_release_metrics.csv
python code/rq3.py --model DS --judgments /path/to/final_ds_judgments.jsonl
python code/rq3.py --model QW --judgments /path/to/final_qw_judgments.jsonl
```


```shell
python code/run_llm.py --requests-path requests_stage1.jsonl --output-dir runs/stage1 --model deepseek-chat --api-key-env DEEPSEEK_API_KEY --run-batch-id example_stage1 --temperature 0.1
python code/run_llm.py --requests-path requests_stage2.jsonl --output-dir runs/stage2 --model deepseek-chat --api-key-env DEEPSEEK_API_KEY --run-batch-id example_stage2 --temperature 0.1
```


```shell
python code/parse_model_outputs.py --raw runs/stage1/raw_responses.jsonl --output runs/stage1/reparsed_outputs.jsonl
```


