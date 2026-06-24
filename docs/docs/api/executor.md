# Executor & Options

This page documents `ToolOptions`, `ExecutorOpts`, and `ExecutionContext` — the classes used to configure how tool functions are executed.

## ToolOptions

::: ivcap_lambda.builder.ToolOptions

---

## ExecutorOpts

::: ivcap_lambda.executor.ExecutorOpts

---

## ExecutionContext

::: ivcap_lambda.executor.ExecutionContext

---

## Executor (internal)

The `Executor` class manages the thread pool and job result cache. It is created automatically by `add_tool_api_route` based on `ToolOptions.executor_opts`. You do not normally need to interact with it directly.

::: ivcap_lambda.executor.Executor
