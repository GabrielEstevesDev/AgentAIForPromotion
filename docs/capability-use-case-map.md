# AI Capability-to-Use-Case Map for Commerce

This document maps Aria's AI capabilities to specific client workflows, pain points, and pilot recommendations. Use this when helping prospects understand what AI can do for their commerce operations.

## Capability Map

| Capability (Tools) | Client Workflow | Pain Point Solved | Benefiting Teams | Pilot Scope |
|---|---|---|---|---|
| query_library + python_executor | Revenue analytics & executive dashboards | "We spend hours building weekly reports" | Merchandising, Executive | 30 days, all SKUs |
| stockout_risk + reorder_with_cost → HITL | Automated replenishment | "We run out of stock because nobody monitors velocity" | Ops, Procurement | 30 days, top 50 SKUs |
| rag_search + sql_query | Policy-aware customer response | "Support agents spend 10 min per ticket looking up policies" | Customer Success | 30 days, 50 tickets |
| rag_search + sql_query → HITL | Refund decision support | "Refund decisions are inconsistent across agents" | CS, Finance | 30 days, all refund requests |
| sql_query + python_executor → HITL | Data-driven promotion planning | "Promos are based on gut feel, not data" | Marketing, Merchandising | 1 campaign cycle |
| web_search + sql_query | Competitive & market intelligence | "We don't know how market trends affect our catalog" | Strategy, Merchandising | On-demand |
| customer_segments + high_rated_low_sales | Customer & product opportunity mapping | "We don't know which products to push to which segments" | Marketing, Merchandising | 30 days |

## Typical Pilot Structure

### Phase 1 — Quick Win (Days 1-14)
- Connect order history and product catalog
- Deploy automated reporting (revenue, inventory, customer segments)
- Estimated time saved: 8-12 hours/week on manual reporting

### Phase 2 — Decision Support (Days 15-30)
- Enable HITL workflows for promotions and replenishment
- Set up policy-aware customer response drafting
- Estimated impact: 20-30% faster decision cycles

### Phase 3 — Scale (Days 31-60)
- Expand to full catalog monitoring
- Add competitive intelligence automation
- Measure ROI against baseline KPIs

## ROI Benchmarks

- **Manual reporting replacement**: $2,000-5,000/month in analyst time
- **Stockout prevention**: 3-8% revenue lift from reduced out-of-stock events
- **Promotion optimization**: 15-25% improvement in campaign ROI vs. gut-feel planning
- **Customer response**: 60-70% reduction in time-to-resolution for policy queries
