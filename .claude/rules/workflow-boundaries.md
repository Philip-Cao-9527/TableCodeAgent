# Workflow 边界补充规则

- `product workflow` 可以使用产品态工具和 repair feedback 来帮助用户完成真实表格任务，但不得把内部 oracle 当作答案来源。
- `helper-assisted workflow` 只服务本地 fixture、pytest、validator、simulated Agent regression 和问题归因。
- `no-helper capability evaluation` 必须禁用产品主 Loop 工具和测试 oracle 路径，模型只能基于公开 task、表格文件、允许库和 output schema 生成 `solve.py`。
- 新增 workflow、task contract、answer schema、validator、runner prompt 或业务断言后，先补本地 deterministic 和模拟错误输出回归，再考虑真实 API。
