# vendor/ — 可选第三方工具

本目录存放**不随仓库分发**的可选外部工具。默认被 `.gitignore` 忽略（仅本说明文件入库），
因为它们是"安装步骤 / 独立可配置路径"，而不是仓库源码。

## PostFlow（国内多平台发布 CLI）

`s6_publish/publish.py` 需要 PostFlow 才能真发抖音/小红书/视频号。
缺失时不是崩溃：`tools/health_check.py` 会把它报成 `DEGRADED`，发布阶段进入人工处理。

安装方式二选一：

1. 放到本目录：`vendor/postflow`，其可执行文件为
   `vendor/postflow/.venv/Scripts/postflow.exe`（Windows）。
2. 放到任意目录，并设置：

   ```powershell
   $env:AYHMJ_POSTFLOW_DIR = "D:\tools\postflow"
   # 或写进 config/default.yaml: paths.postflow_dir
   ```

安装后运行 `python tools/health_check.py` 应看到 `postflow READY`。
