# 失败样本回流报告

> 生成时间：2026-07-26 13:27

## 一、角色档案回流

无角色档案需要回流（没有发现 badcase 或为 dry-run）。

## 二、编排提示回流

无编排提示需要回流。

## 三、回流验证计划

以下 1 个场景需在回流后重跑验证：

| 场景 | 后端 | 回流前综合分 |
|------|------|------------|
| 道德灰色地带 | deepseek | 4.6 |

### 验证方法

```bash
# 重跑 道德灰色地带 (deepseek)
python scripts/run_eval.py --scenario moral_gray_zone --backend deepseek
```

重跑后对比 `before_weighted_score` 与新的 `weighted_score`，验证回流效果。