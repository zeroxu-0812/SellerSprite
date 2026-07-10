# 卖家精灵关键词搜索爬虫

输入亚马逊关键词 → 抓取卖家精灵扩展展示的商品数据（亚马逊字段 + 卖家精灵增强指标），落地 CSV/JSON。

## 安装
    pip install -r requirements.txt
    playwright install chromium

## 配置鉴权
复制 `.env.example` 为 `.env`，填入从卖家精灵扩展 devtools 抓包得到的：
    KEEPA_AUTH_TOKEN=...
    KEEPA_AUTH_FP=...
    KEEPA_RANDOM_TOKEN=...
    KEEPA_COOKIE=...        # 可选

token 过期后重新抓包更新（或配 KEEPA_TOKEN_REFRESH_COMMAND 自动刷新）。

## 运行
    python keyword_pipeline.py
    # 输入关键词回车；q 退出

## 输出
`output/keyword_{关键词}_{日期}/`：
- `products.csv` / `products.json`：每个商品一行；冲突字段格式 `值(亚马逊) / 值(卖家精灵)`
- `market_overview.csv` / `market_overview.json`：派生市场总览

## 测试
    python -m pytest -v

## 设计文档
见 `docs/2026-07-10-si-keyword-search-design.md`。

## 范围说明
- v1 市场总览为样本派生（均价/总销量/分布/集中度），**不含真实搜索量**（需 Phase 2 另抓关键词接口）。
- 亚马逊抓取可能遇反爬，必要时调 `config.json` 的 `amazon.page_delay_*` 或加代理。
