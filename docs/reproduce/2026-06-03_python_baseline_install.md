# Python baseline 安装记录

## 当前目标

验证 claude-code-from-scratch Python 版 baseline 的基础安装流程，为后续 TableCodeAgent 表格任务改造做准备。

## 当前状态

- 已完成：创建 TableCodeAgent 私有仓库
- 已完成：初始化 clean main 分支
- 已完成：创建 Python 3.11 conda 环境 tca
- 已完成：安装 Python 版 baseline
- 已完成：验证 mini-claude-py --help 可以正常启动
- 待验证：配置 API 后跑通一轮 Agent Loop
- 待实现：TableCodeAgent 表格工具、验证工具、轨迹日志、任务转换、benchmark 和失败分析

## 环境信息

- 平台：AutoDL Ubuntu
- Conda 环境：tca
- Python：3.11.15
- 安装目录：~/workspace/TableCodeAgent/python
- 验证命令：mini-claude-py --help

## 下一步

配置 OpenAI-compatible API，运行一个最小 Agent 任务，验证模型调用、工具调用和终端交互是否正常。
