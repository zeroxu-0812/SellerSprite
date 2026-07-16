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

### L12. `competitor-lookup/US` 是比 `quick-view` 更优的"单接口全量"端点
- `quick-view` 只给卖家精灵增强（~37 字段），需配合亚马逊抓取 + 合并。
- `competitor-lookup/US?asins=...`（注意路径无 `/quick-view`）**一个接口返回 57 字段**：亚马逊侧（title/price/rating/reviews/image/url/badges）+ 增强（units/amount/profit/BSR/sellers）+ 独家（`amz_unit_trends` 月销量序列、`seller_dto` 卖家公司全称/地址/国别、`reviews_delta` 评论增长、`questions`）。
- **关键**：competitor-lookup 的 `price` 是**正确 USD 价**，而亚马逊页面抓取受机房 geo-IP 影响会返回本地货币（HKD 等）。
- `tk` 签名算法与 quick-view 完全一致（over asins）。
**规则**：有 ASIN 时优先用 competitor-lookup（全、准、单接口）。本项目最终定型为 **ASIN-only**：删掉关键词搜索，只保留 competitor-lookup 全量路径（见 L13/L14 重构）。

## 六、并发与重构（ASIN-only 重构）

### L13. Playwright sync API 在 ThreadPoolExecutor 里并发是可行的——只要每个任务自管生命周期
并发抓折扣页时，多个线程各自 `sync_playwright()` → launch → close。实测无 greenlet / 线程错误。
**关键**：每个任务**独立拥有**自己的 Playwright 实例与 browser（不跨线程共享对象）；`sync_playwright()` 的线程绑定约束是"不能跨线程**复用**同一实例"，不是"不能多线程各自**新开**"。因此"每线程一个完整生命周期"的模式安全。
**规则**：要并发跑 Playwright 抓取，用 ThreadPoolExecutor + 每任务自管 `sync_playwright()` 块即可；别想跨线程共享同一个 browser/page。

### L14. 亚马逊图片 ID 正则要容错特殊字符，且尺寸码分隔符是 `._`
`large_image_url` 旧正则 `/images/I/([A-Za-z0-9]+)\.` 两处错：①图片 ID 含 `+`（如 `71+oszjnRVL`）→ `[A-Za-z0-9]+` 在 `+` 处截断、`\.` 对不上 → 整条不匹配，高清图没派生成（仍是 200px）；②尺寸码格式是 `{ID}._AC_US200_.jpg`，`.` 后跟的是 `_` 不是大写字母。
**规则**：用 `/images/I/([^/.]+?)\._` —— ID 允许除 `/`、`.` 外任意字符（含 `+` `%`），到 `._` 这个稳定分隔符停。改完用含 `+` 的真实 ID 补回归测试。

### L15. 并发改造要把"共享可变状态"的锁想清楚，别只盯请求层
加并发时容易只想着"多线程发请求"，忽略共享状态：①`KeepaTokenManager` 的登录子进程——多线程同时发现 token 过期会各起一个登录进程、竞争写缓存文件；②`invalidate_cache` 的 `unlink` 多线程同时删会抛 FileNotFoundError。
**规则**：并发改造清单 = 请求并发 + **所有共享可变状态的锁/幂等**。这里给 refresh 加锁 + 双检缓存（拿到锁后复看缓存，已被别的线程刷新就直接复用），`unlink(missing_ok=True)` 容忍并发删除。

### L16. 本地 HTML 报表要"内联注入"，别用 fetch——`file://` 下 fetch 被 CORS 拦
旧的 products.html 用 `fetch('products.csv')` 取数据，但流水线已改成只产 JSON，且**双击 `file://` 打开时浏览器 CORS 直接拦掉 fetch**——结果打开是空表。改造为：Python 把 `{products, overview}` 的 JSON **内联**到模板的 `/*__DATA__*/…/*__END__*/` 占位之间，生成自包含 HTML，双击即看、无需服务器。
**规则**：①面向"双击查看"的本地 HTML，数据要内联，不能依赖 fetch/XHR（file:// 下被拦）。②把 JSON 塞进 `<script>` 时，必须把 `</` 转义成 `<\/`，否则商品标题里出现 `</script>` 会截断脚本块。③渲染器要跟数据形状对齐：本项目 `clean_row` 丢掉了 `bsr_list`/`trends` 原始 JSON（只留扁平键 + `amz_unit_trend` 的 `{YYYYMM:count}` 映射），渲染函数必须改用这些键，不能沿用旧的数组形状。

### L17. competitor-lookup 销量字段分父体/子体：units/amount 是父体聚合，month_units/sub_total_amount/amz_unit_trend 是查询的本子体
查的都是子 ASIN（每条 `parent` 指向父 ASIN），但接口把**父体（变体家族）聚合**当 headline：`units`×`price` 恒等于 `amount`（父体销量/销售额），`month_units`×`price`≈`sub_total_amount`（本子体）。`amz_unit_trend`（月销序列）量级贴近 `month_units`（子体），而非父体的 `units`。products.html 销量块曾把 `month_units` 标成「父体」、`units` 标成「子体」→ 反了。
**规则**：渲染销量 父体=`units`、子体=`month_units`（金额同理 父体=`amount`、子体=`sub_total_amount`）；趋势 `amz_unit_trend` 是查询的本子体月销序列。判据：`sub_total_amount`（"sub"=子体）恒小于 `amount` 且与 `month_units` 配对，`units` 恒大于 `month_units`（父体聚合 > 单子体）。

**补充（实测坐实）**：competitor-lookup 返回**两条**月销序列——`amzUnitTrends`（页面渲染用的 `amz_unit_trend`）量级贴合 `month_units`，是**子体**；另一条 `trends` 量级贴合 `units`，是**父体**月销。父 ASIN 本身在接口里"无数据"（变体父体非独立在售 listing），无法直接查父体核对，靠两条序列分别对标 `units`/`month_units` 判定。`clean_row` 目前把 `trends`（父体）和 `amz_unit_trends`（原始 list）当冗余 JSON 丢弃，所以页面只显示子体趋势；若要显示父体趋势需保留/派生 `trends`。

### L18. "ltd/限时折扣"不在卖家精灵 badges，在亚马逊页 dealBadge；折扣价抓取要 deal 门控 + 伪折扣守卫
competitor-lookup **不含任何折扣/deal/listPrice 字段**（折扣只能抓亚马逊页），`badges` 也只有 AC/BS/NR/EBC/V 这类，**没有 ltd**。所谓 ltd 是亚马逊详情页的 `class="dealBadge"`（DealsX）+ 倒计时（`dealsCountdownTimer`/`deal_expiry_timer`）。曾误把示例产品公司名里的 "Ltd" 当成 deal 标记——别犯。
**规则**：①判 deal 用 `_has_deal(html)`（dealBadge 或倒计时），**无 deal 不取折扣**（普通 MSRP 划线价不当折扣）。②亚马逊页第一处 `a-offscreen` 不一定是主价（可能取到变体/样品价 HKD1.72 → 99% 伪折扣），且很多 deal 页无 `#corePrice_feature_div` 等标准块、选择器救不了；故对折扣% 设上限 90%，超阈判抓错、丢弃（显示无折扣 > 伪 99%）。

