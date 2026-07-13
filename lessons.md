# Lessons（卖家精灵关键词搜索爬虫）

> 按 code_standards.md 自我提升循环维护。只记非显而易见、易重犯的模式。每次会话开始回顾。

## 一、规划 / TDD

### L1. 写 TDD 计划时，测试期望值必须能"算穿"实现的真实行为
本次 plan 出现 3 处测试与实现自相矛盾，都是实现者/评审抓出来的：
- `CANONICAL_FIELD_MAP` 里 `sellers→seller_count` 会把键改名，破坏 `merged["sellers"]` 断言（T3）。
- `top10_units_share` 字段名是 top-10，但测试期望值 `90/170` 是 top-1（T6）。
- impl 用 `utf-8-sig` 写 CSV、`_safe_name` 把空格转下划线，但测试按裸读/含空格断言（T7）。
**规则**：定稿前，把每个测试期望值**手动代入实现的代码路径**走一遍；字段改名、编码、归一化等副作用要算进期望。否则实现者要么照抄出错、要么"信测试改实现"导致语义错误（T6 就这样把 top-10 误改成 top-1）。

### L2. 子代理驱动开发时，让实现者"信测试"是危险的
实现者倾向于把测试当合同、改实现去迎合。当测试本身错了（L1），这会把语义改歪。
**规则**：实现者报 DONE_WITH_CONCERNS 说"测试与实现矛盾"时，**先判断哪边对**（通常是实现/字段名语义），别默认测试正确。评审要看实现者是否为了过测试而扭曲了语义。

## 二、工具 / Bash

### L3. `cmd | tail && next` 会用 tail 的退出码门控，掩盖真实失败
我用 `pytest -q 2>&1 | tail -4 && git commit` 提交了一个**语法错误**的测试——因为管道退出码取的是 tail（恒 0），不是 pytest。
**规则**：用测试结果门控提交时，**不要管道**：`pytest -q && git commit`；或 `pytest; [ $? -eq 0 ] && commit`。要看输出又想门控，分开两步。

## 三、卖家精灵领域知识（硬实证）

### L4. 卖家精灵扩展**没有"关键词→商品"接口**
扩展在亚马逊页面的工作流是：**自己抓亚马逊 HTML 得 ASIN** → 调 `quick-view` 给 ASIN 加增强指标。关键词→商品这件事是**亚马逊干的**，卖家精灵只增强 ASIN。
**规则**：别假设插件有某能力——**抓包验证**。本项目因此被迫做成"两段流水线"（Playwright 抓亚马逊 + quick-view 增强）。

### L5. `tk` 反爬签名是**输入无关**的 TKK 算法
`token_calculate(text, tkk)` 对任意 UTF-8 字符串（单 ASIN、逗号拼接多 ASIN、关键词、email+密码）都一样。复制 keepa-monitor 的实现即可，换接口只需换"喂进去的字符串"。version 变了（5.0.2→5.0.4）要重算 tkk 种子。

### L6. 卖家精灵登录态寿命极短（分钟级），必须自动刷新
静态抓包 token 几分钟就过期（服务器返回 `code:ERR_NEED_RE_AUTHORIZED / "令牌过期"`）。
**登录刷新流程（已实测）**：
- `GET https://www.sellersprite.com/v2/extension/signin?email=<u>&password=<md5>&tk=<sig(email+md5pwd)>&version=5.0.4&language=zh_CN&extension=<id>&source=chrome`
- 响应 `data.token` = 新鲜 **auth-token**。
- **auth-fp / random-token 是客户端稳定值，signin 不返回**——从扩展抓任意一条请求头取一次，放 `.env` 长期复用（random-token 是 UUID 永不变；auth-fp 偶尔轮换，失效就重抓）。
**规则**：从第一天就接 `KEEPA_TOKEN_REFRESH_COMMAND` 自动登录，别靠手动抓 token。

### L7. `code:OK` 不代表有数据；`-1` 是"无数据"哨兵
quick-view 对无销量数据的 ASIN 返回 `units=-1`（其余字段 None），但外层 `code:"OK"`。直接求和会把 -1 算进去。
**规则**：解析层把已知不可能为负的指标字段（units/amount/profit/sellers…）的 `-1` 归一为 None。负值合法的字段（bsr_cr 增长率等）不要动。

### L8. 鉴权失效检测要靠"码 + 文本"双判，且码清单要靠实测补
服务器会换错误码（实测到 `ERR_NEED_RE_AUTHORIZED`、参考实现里有 `ERR_GLOBAL_SESSION_EXPIRED`）。光靠 message 文本匹配脆弱（措辞会变）。
**规则**：`AUTH_EXPIRED_CODES` 维护成集合，每发现新码就加；同时保留 message 兜底。线上真跑出来的码最可信。

## 四、测试方法

### L9. 单元测试（fixture）验证逻辑，但只有**真实 live 跑**才暴露数据层怪癖
单测全绿的代码，live 跑才发现：`-1` 哨兵（L7）、新鉴权码（L8）、geo-IP 返回 HKD 价格、部分 ASIN 无增强数据。
**规则**：声明"完成"前必须做一次**真实端到端冒烟**（真 token/真网络），并据此回头补单测（L7/L8 的测试都是 live 后补的）。

### L10. token 有效性先单独直测，别让 Playwright 白跑
验证 Leg B 鉴权时，先用一个 2 秒的直连 quick-view 调用确认 token/签名有效，再跑完整管道（含几十秒的 Playwright）。token 过期就直接定位，不浪费一次抓取。
**规则**：分层验证——签名→单接口→全管道，从便宜到贵。

## 五、合并多源数据

### L11. 同字段多源冲突时，单格双值 + 来源标注，优于二选一
亚马逊与卖家精灵对 BSR/卖家数/重量等同字段各有快照，值常不同（时间差/定义差）。
**规则**：合并单位=**叶子字段**（先扁平化）；两源不同→`值A(亚马逊) / 值(卖家精灵)` 同格对照；单源→裸值；相同→单值。别丢任何一边。
