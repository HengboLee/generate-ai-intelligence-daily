# 📊【{{brand}}】{{report_date}} AI 情报合集

> 统计窗口：{{window}}｜生成时间：{{as_of}}｜通过核验：{{selected_news}} 条新闻、{{selected_interview}} 条面试内容

## 🌐 AI 大事件日报

**今日速览：** {{news_overview}}

### 🏆 全球 AI 大事件 Top {{selected_news}}

1. **{{title}}**【事件日期：{{event_date}}】【发布日期（{{timezone}}）：{{published_date}}】{{stars}}
   - {{summary}}
   - **为什么重要：** {{why_it_matters}}
   - **来源：** [{{source_name}}]({{source_url}}){{additional_sources}}

> 条目不足上限时，不补入低可信或过期信息。

## 🎯 AI 面试日报

> 本栏默认是基于已核验新闻、论文、技术文章或官方 JD 生成的模拟题/知识卡，不等同于真实面经。

**今日速览：** {{interview_overview}}

### 🎯 今日面试内容 Top {{selected_interview}}

1. **「{{question_type}}｜{{role}}」{{question}}**
   - **考察点：** {{focus}}
   - **回答框架：**
     - {{answer_step}}
   - **依据：** [来源]({{source_url}})

## 核验备注

- 事件日期与发布日期分开记录；原文未明确事件日期时标注“未单独披露”。
- 发布日期统一换算到配置时区；原始页面显示的日期可保留在事件日期说明中。
- 官方原始材料可单源入选；重大非官方结论至少需要两个独立来源。
- 本日报只保留短摘要和来源链接，不复制原文全文。
