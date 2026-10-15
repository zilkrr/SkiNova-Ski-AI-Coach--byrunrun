# Cursor 接手说明

## 现在怎么运行

在当前 `skipro` 目录执行 `python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload`，浏览器打开 `http://127.0.0.1:8765`。界面必须从服务打开，不能双击 HTML。

## 可以直接发给 Cursor 的话

> 这是我的 Ski Pro / SkiNova 课程原型升级项目。请先读 README.md、app/main.py、app/services.py 和 web/app.js，确认 API 契约，再调整 web/index.html 和 web/style.css 的界面。保留训练计划、历史记录、日志 CSV 导出、视频上传/检查/删除、英文内容页与 SEO CSV 导入功能。可以借鉴 legacy/index.html 的暗色滑雪风格，但不要恢复其中的模拟分数、模拟诊断和静默本地回退。模型未配置时必须显示规则模板，视频只做文件检查；不要在 UI 中承诺姿态识别、实时技术打分或真实流量增长。所有用户输入必须安全显示，保留加载中、空状态、失败提示、移动端适配。更改交互后运行 python -m unittest discover -s tests -v，并在浏览器验证创建计划、写日志、刷新恢复和导入 CSV。

## API 契约

| Method / path | 输入 | 输出 |
|---|---|---|
| GET /api/health | 无 | 存储、规则/配置模型状态；configured 不等于模型在线 |
| POST /api/plans | sport: ski/snowboard；level: beginner/intermediate/advanced；minutes:20–120；goal:1–500 字符 | 已保存计划、时间块、source、model；可能有 fallback notice |
| GET /api/plans | 浏览器 cookie | 当前会话最近 100 个计划 |
| POST /api/logs | plan_id、date (YYYY-MM-DD)、minutes:1–480、effort:1–10、note | 关联当前会话计划的日志 |
| GET /api/logs | cookie | 最近 100 条日志与对应时长合计 |
| GET /api/logs/export | cookie | 最近 100 条日志 CSV；文本防公式注入 |
| POST /api/videos?filename=… | 原始二进制文件，不是 FormData；最多 30MB | 记录 id、文件名、大小 |
| GET /api/videos | cookie | 当前会话文件列表 |
| POST /api/videos/{id}/inspect | cookie | 可解码性、宽高、帧率、时长；无人体姿态评分 |
| DELETE /api/videos/{id} | cookie | 204；删除文件和记录 |
| POST /api/seo/analyze | {"csv":"CSV 文本"} | 指标、query 聚合、建议；不保存 CSV |
| GET /api/seo/sample | 无 | source:synthetic-demo，合成示例 |

错误统一读取 HTTP 状态和 `detail`。不要改成“失败后展示一套成功结果”。同源 cookie 自动发送，不要改成跨域硬编码 localhost:8000。

## 旧版代码的定位

`legacy/` 是原样保存的旧版本，用于回看视觉风格。它含固定诊断分数、非持久化状态和外部媒体，只作历史参考。新项目从 `app/main.py` 启动。原有教练商城/GPS 没有作为新 MVP 的已验证能力保留；本轮重点是训练闭环、内容和可解释数据分析。

## 面试演示顺序（约 3 分钟）

1. 选择运动、水平、时间，生成规则计划，解释可选模型与回退。
2. 写一条训练反思，刷新页面，确认数据还在；导出 CSV。
3. 上传自己可分享的小视频，检查元数据，说明姿态识别仍是后续工作。
4. 打开英文文章，展示每页 URL、标题、描述、内链。
5. 用合成 GSC 示例演示 CTR 与加权排名，强调它不是项目真实流量。

演示前自己完整操作一遍，尤其要能解释 SQLite、浏览器 cookie 和 CTR 的计算。
