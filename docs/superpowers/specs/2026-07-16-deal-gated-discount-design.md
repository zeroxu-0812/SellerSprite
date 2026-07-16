# 折扣门控（仅真实 deal 显示折扣）设计

- 日期：2026-07-16
- 状态：已批准，待实现
- 涉及文件：改 `amazon_search.py`；测试 `tests/test_amazon_search.py`

## 背景

现管线对**每个**产品都抓亚马逊详情页取折扣（`list_price` 划线价 + `discount_off_list_pct`）。问题：普通产品的 MSRP 划线价也会被当成折扣，产出伪折扣（如曾出现 99% off 的脏数据）。

用户诉求：**仅当产品是真实限时 deal（ltd）时才抓取并展示折扣（折扣前/折扣后/折扣%）；其他「历史价格」不展示。**

## 关键核实（已实测）

- `ltd`/deal **不是卖家精灵 `badges` 值**：示例 `B0DSVT64CL` 的 sellersprite `badges=["EBC"]`，全字段唯一的 "ltd" 是卖家公司名里的 "Ltd"。
- 该产品亚马逊页**确为真实限时 deal**：含 `class="dealBadge"`（Amazon DealsX 徽标）+ 倒计时。
- sellersprite competitor-lookup **不含任何折扣/deal 字段**（折扣只能靠抓亚马逊页）。
- 结论：deal 信号在**亚马逊页**上，无法靠 sellersprite 预判跳过抓取。

## 设计

### `amazon_search.py`

新增 `_has_deal(html) -> bool`：页面含 deal 徽标（`class="…dealBadge"`）或倒计时（`dealsCountdownTimer`/`deals_countdown_timer`/`deal_expiry_timer`）即为真 deal。

`parse_price_detail(html)` 顶部加门控：**无 deal 直接返回折扣全 None**（不取 `list_price`/`price_current`/`discount_off_list_pct`）。有 deal 才走原逻辑取折扣。

**额外健全性守卫**：deal 页有时第一处 `a-offscreen` 取到变体/样品价（如 `HKD1.72`），算出 99% 伪折扣；且这些页无标准价格块（`#corePrice_feature_div` 等取不到）无法靠选择器纠正。故对折扣% 设上限 `_MAX_PLAUSIBLE_DISCOUNT_PCT = 90`：算出的折扣 > 90% 视为抓错现价，**不设折扣**（显示无折扣 > 显示伪 99%）。真实限时 deal 折扣极少超 90%，正常 deal（如 `B0DSVT64CL` 的 19%）不受影响。

下游 `_enrich_detail` 不变：仍用 `discount_off_list_pct`（None 时不设 `list_price`）。`about` 抽取不变（所有页都抓、不展示）。

### 展示层

不动。`products.html` 价格列本就是「有 `list_price`/`discount_off_list_pct` 才显示划线价 + -折扣%」。deal 门控后，仅 deal 产品有这些字段 → 仅它们显示折扣；伪划线价消失。

### 抓取量

仍抓所有产品详情页（deal 信号在页上、about 也要抓，无法预判跳过）。本次改动**不省抓取量**，只清掉伪折扣。

## 测试（TDD，纯函数）

`parse_price_detail` / `_has_deal` 为纯函数，加测试：
- `_has_deal`：dealBadge / 倒计时 → True；普通划线 / 空 → False。
- `parse_price_detail`：有 dealBadge + 划线 + 现价 → 给折扣%；**无 dealBadge（哪怕有划线价）→ 折扣全 None**（证明门控）；**deal 页但现价抓错(99%) → 折扣 None**（守卫）。

## 非目标

不加「限时折扣」标签列；不跳过页面抓取；不改 about；不改展示层。

## 验收

- 重新抓取：真实 deal 产品（如 `B0DSVT64CL`）显示折扣前/后/%；非 deal 产品价格列只显现价（无伪划线/伪折扣%）。
- 全量 pytest 绿。
