# Pre-built SQL queries for the e-commerce database.
# Keys are the query names the agent uses. Values are ready-to-run SELECT statements.
# Add new entries here to expand coverage without touching the tool code.

QUERY_LIBRARY: dict[str, dict] = {

    # ── Sales & Revenue ──────────────────────────────────────────────────────
    "total_revenue": {
        "description": "Total revenue across all non-cancelled orders",
        "sql": """
SELECT
    COUNT(*) AS total_orders,
    ROUND(SUM(totalAmount), 2) AS total_revenue,
    ROUND(AVG(totalAmount), 2) AS avg_order_value
FROM "Order"
WHERE status != 'Cancelled'
""".strip(),
    },
    "revenue_by_month": {
        "description": "Monthly revenue excluding cancelled orders (last 12 months, excluding cancelled)",
        "date_range_days": 365,
        "sql": """
SELECT
    strftime('%Y-%m', orderDate) AS month,
    COUNT(*) AS orders,
    ROUND(SUM(totalAmount), 2) AS revenue
FROM "Order"
WHERE status != 'Cancelled'
  AND orderDate >= date('now', '-12 months')
GROUP BY month
ORDER BY month ASC
""".strip(),
    },
    "revenue_by_category": {
        "description": "Total revenue broken down by product category (all time, excluding cancelled)",
        "sql": """
SELECT
    p.category,
    COUNT(DISTINCT o.id) AS orders,
    SUM(oi.quantity) AS units_sold,
    ROUND(SUM(oi.quantity * oi.unitPrice), 2) AS revenue
FROM OrderItem oi
JOIN Product p ON oi.productId = p.id
JOIN "Order" o ON oi.orderId = o.id
WHERE o.status != 'Cancelled'
GROUP BY p.category
ORDER BY revenue DESC
""".strip(),
    },

    # ── Products ─────────────────────────────────────────────────────────────
    "top_products_by_revenue": {
        "description": "Top 10 products ranked by total revenue (excluding cancelled)",
        "sql": """
SELECT
    p.name,
    p.category,
    SUM(oi.quantity) AS units_sold,
    ROUND(SUM(oi.quantity * oi.unitPrice), 2) AS revenue
FROM OrderItem oi
JOIN Product p ON oi.productId = p.id
JOIN "Order" o ON oi.orderId = o.id
WHERE o.status != 'Cancelled'
GROUP BY p.id, p.name, p.category
ORDER BY revenue DESC
LIMIT 10
""".strip(),
    },
    "top_products_by_quantity": {
        "description": "Top 10 products ranked by units sold",
        "sql": """
SELECT
    p.name,
    p.category,
    SUM(oi.quantity) AS units_sold,
    ROUND(SUM(oi.quantity * oi.unitPrice), 2) AS revenue
FROM OrderItem oi
JOIN Product p ON oi.productId = p.id
JOIN "Order" o ON oi.orderId = o.id
WHERE o.status != 'Cancelled'
GROUP BY p.id, p.name, p.category
ORDER BY units_sold DESC
LIMIT 10
""".strip(),
    },
    "products_by_category": {
        "description": "All products grouped by category with price range",
        "sql": """
SELECT
    category,
    COUNT(*) AS product_count,
    ROUND(MIN(price), 2) AS min_price,
    ROUND(MAX(price), 2) AS max_price,
    ROUND(AVG(price), 2) AS avg_price
FROM Product
GROUP BY category
ORDER BY product_count DESC
""".strip(),
    },
    "top_rated_products": {
        "description": "Top 10 products by average review rating (min 3 reviews)",
        "sql": """
SELECT
    p.name,
    p.category,
    ROUND(AVG(r.rating), 2) AS avg_rating,
    COUNT(r.id) AS review_count
FROM Review r
JOIN Product p ON r.productId = p.id
GROUP BY p.id, p.name, p.category
HAVING review_count >= 3
ORDER BY avg_rating DESC, review_count DESC
LIMIT 10
""".strip(),
    },
    "products_without_reviews": {
        "description": "Products that have no reviews yet",
        "sql": """
SELECT p.name, p.category, ROUND(p.price, 2) AS price
FROM Product p
LEFT JOIN Review r ON r.productId = p.id
WHERE r.id IS NULL
ORDER BY p.category, p.name
""".strip(),
    },

    # ── Inventory ────────────────────────────────────────────────────────────
    "low_stock": {
        "description": "Products with stock level below a threshold. Default threshold is 10. Pass params_json with 'threshold' to override (e.g. {\"threshold\": 20} for stock < 20).",
        "parameterized": True,
        "sql": "",
    },
    "out_of_stock": {
        "description": "Products currently out of stock",
        "sql": """
SELECT
    p.name,
    p.category,
    i.lastRestock
FROM Inventory i
JOIN Product p ON i.productId = p.id
WHERE i.stockLevel = 0
ORDER BY i.lastRestock ASC
""".strip(),
    },
    "inventory_overview": {
        "description": "Stock level summary by category",
        "sql": """
SELECT
    p.category,
    COUNT(*) AS products,
    SUM(i.stockLevel) AS total_units,
    MIN(i.stockLevel) AS min_stock,
    MAX(i.stockLevel) AS max_stock,
    ROUND(AVG(i.stockLevel), 1) AS avg_stock
FROM Inventory i
JOIN Product p ON i.productId = p.id
GROUP BY p.category
ORDER BY total_units ASC
""".strip(),
    },
    "top_products_by_inventory": {
        "description": "Products ranked by stock level (highest inventory first)",
        "sql": """
SELECT
    p.name,
    p.category,
    i.stockLevel,
    i.lastRestock
FROM Inventory i
JOIN Product p ON i.productId = p.id
ORDER BY i.stockLevel DESC
LIMIT 50
""".strip(),
    },

    # ── Orders ───────────────────────────────────────────────────────────────
    "orders_by_status": {
        "description": "Order count and total revenue grouped by status",
        "sql": """
SELECT
    status,
    COUNT(*) AS order_count,
    ROUND(SUM(totalAmount), 2) AS total_amount,
    ROUND(AVG(totalAmount), 2) AS avg_amount
FROM "Order"
GROUP BY status
ORDER BY order_count DESC
""".strip(),
    },
    "recent_orders": {
        "description": "Last 20 orders with customer name and status",
        "sql": """
SELECT
    c.firstName || ' ' || c.lastName AS customer,
    strftime('%m/%d/%Y', o.orderDate) AS orderDate,
    o.status,
    ROUND(o.totalAmount, 2) AS amount
FROM "Order" o
JOIN Customer c ON o.customerId = c.id
ORDER BY o.orderDate DESC
LIMIT 20
""".strip(),
    },
    "orders_today": {
        "description": "All orders placed today",
        "sql": """
SELECT
    c.firstName || ' ' || c.lastName AS customer,
    strftime('%m/%d/%Y', o.orderDate) AS orderDate,
    o.status,
    ROUND(o.totalAmount, 2) AS amount
FROM "Order" o
JOIN Customer c ON o.customerId = c.id
WHERE date(o.orderDate) = date('now')
ORDER BY o.orderDate DESC
""".strip(),
    },
    "pending_orders": {
        "description": "All orders currently in Pending status",
        "sql": """
SELECT
    c.firstName || ' ' || c.lastName AS customer,
    strftime('%m/%d/%Y', o.orderDate) AS orderDate,
    ROUND(o.totalAmount, 2) AS amount
FROM "Order" o
JOIN Customer c ON o.customerId = c.id
WHERE o.status = 'Pending'
ORDER BY o.orderDate ASC
""".strip(),
    },
    "refund_order_context": {
        "description": "Parameterized HITL helper for refund-email context. Requires params_json with customer_name and optional order_ref.",
        "sql": "",
        "parameterized": True,
    },

    # ── Customers ────────────────────────────────────────────────────────────
    "top_customers_by_spend": {
        "description": "Top 10 customers ranked by total spending",
        "sql": """
SELECT
    c.firstName || ' ' || c.lastName AS customer,
    c.email,
    COUNT(o.id) AS total_orders,
    ROUND(SUM(o.totalAmount), 2) AS total_spent
FROM Customer c
JOIN "Order" o ON o.customerId = c.id
WHERE o.status != 'Cancelled'
GROUP BY c.id, c.firstName, c.lastName, c.email
ORDER BY total_spent DESC
LIMIT 10
""".strip(),
    },
    "new_customers_this_month": {
        "description": "Customers who registered this calendar month",
        "sql": """
SELECT
    firstName || ' ' || lastName AS customer,
    email,
    strftime('%m/%d/%Y', createdAt) AS createdAt
FROM Customer
WHERE strftime('%Y-%m', createdAt) = strftime('%Y-%m', 'now')
ORDER BY createdAt DESC
""".strip(),
    },
    "customer_count": {
        "description": "Total number of registered customers",
        "sql": """
SELECT COUNT(*) AS total_customers FROM Customer
""".strip(),
    },
    "customers_with_most_orders": {
        "description": "Top 10 customers by number of orders placed",
        "sql": """
SELECT
    c.firstName || ' ' || c.lastName AS customer,
    c.email,
    COUNT(o.id) AS order_count
FROM Customer c
JOIN "Order" o ON o.customerId = c.id
GROUP BY c.id, c.firstName, c.lastName, c.email
ORDER BY order_count DESC
LIMIT 10
""".strip(),
    },

    # ── Reviews ──────────────────────────────────────────────────────────────
    "rating_distribution": {
        "description": "Number of reviews per star rating (1–5)",
        "sql": """
SELECT
    rating,
    COUNT(*) AS review_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
FROM Review
GROUP BY rating
ORDER BY rating DESC
""".strip(),
    },
    "recent_reviews": {
        "description": "Last 20 reviews with product name and rating",
        "sql": """
SELECT
    p.name AS product,
    r.rating,
    r.comment,
    strftime('%m/%d/%Y', r.createdAt) AS createdAt
FROM Review r
JOIN Product p ON r.productId = p.id
ORDER BY r.createdAt DESC
LIMIT 20
""".strip(),
    },
    "worst_rated_products": {
        "description": "Bottom 10 products by average rating (min 3 reviews)",
        "sql": """
SELECT
    p.name,
    p.category,
    ROUND(AVG(r.rating), 2) AS avg_rating,
    COUNT(r.id) AS review_count
FROM Review r
JOIN Product p ON r.productId = p.id
GROUP BY p.id, p.name, p.category
HAVING review_count >= 3
ORDER BY avg_rating ASC, review_count DESC
LIMIT 10
""".strip(),
    },

    # ── API Usage ────────────────────────────────────────────────────────────
    "api_usage_last_30_days": {
        "description": "Daily API usage (requests + tokens) for the last 30 days",
        "sql": """
SELECT
    date,
    requestCount,
    totalTokens
FROM ApiUsage
WHERE date >= date('now', '-30 days')
ORDER BY date DESC
""".strip(),
    },
    "api_usage_summary": {
        "description": "Total API requests and tokens consumed all-time",
        "sql": """
SELECT
    COUNT(*) AS days_tracked,
    SUM(requestCount) AS total_requests,
    SUM(totalTokens) AS total_tokens,
    ROUND(AVG(requestCount), 1) AS avg_daily_requests
FROM ApiUsage
""".strip(),
    },

    # ── Suppliers & Purchase Orders ───────────────────────────────────────────
    "suppliers": {
        "description": "List all suppliers with contact info",
        "sql": """
SELECT name, email, phone, id
FROM Supplier
ORDER BY name
""".strip(),
    },
    "purchase_orders": {
        "description": "All purchase orders with supplier name and item count",
        "sql": """
SELECT
    s.name AS supplier,
    po.status,
    po.totalAmount AS total,
    COUNT(poi.id) AS items,
    strftime('%m/%d/%Y', po.createdAt) AS createdAt
FROM PurchaseOrder po
JOIN Supplier s ON po.supplierId = s.id
LEFT JOIN PurchaseOrderItem poi ON poi.purchaseOrderId = po.id
GROUP BY po.id
ORDER BY po.createdAt DESC
""".strip(),
    },
    "sales_velocity": {
        "description": "Sales velocity per product (units sold per day) over the last 30 days, with current stock",
        "sql": """
SELECT
    p.sku,
    p.name,
    p.category,
    p.price,
    COALESCE(i.stockLevel, 0) AS currentStock,
    COALESCE(SUM(oi.quantity), 0) AS unitsSold30d,
    ROUND(COALESCE(SUM(oi.quantity), 0) / 30.0, 2) AS dailyVelocity,
    CASE
        WHEN COALESCE(SUM(oi.quantity), 0) > 0
        THEN ROUND(COALESCE(i.stockLevel, 0) / (COALESCE(SUM(oi.quantity), 0) / 30.0), 1)
        ELSE 999
    END AS daysOfStock
FROM Product p
LEFT JOIN Inventory i ON i.productId = p.id
LEFT JOIN OrderItem oi ON oi.productId = p.id
LEFT JOIN "Order" o ON oi.orderId = o.id
    AND o.status != 'Cancelled'
    AND o.orderDate >= date('now', '-30 days')
GROUP BY p.id, p.sku, p.name, p.category, p.price, i.stockLevel
ORDER BY daysOfStock ASC
""".strip(),
    },
    "replenishment_candidates": {
        "description": "Products that need replenishment — low stock AND positive sales velocity",
        "sql": """
SELECT
    p.sku,
    p.name,
    p.category,
    ROUND(p.price, 2) AS price,
    COALESCE(i.stockLevel, 0) AS currentStock,
    COALESCE(SUM(oi.quantity), 0) AS unitsSold30d,
    ROUND(COALESCE(SUM(oi.quantity), 0) / 30.0, 2) AS dailyVelocity,
    CASE
        WHEN COALESCE(SUM(oi.quantity), 0) > 0
        THEN ROUND(COALESCE(i.stockLevel, 0) / (COALESCE(SUM(oi.quantity), 0) / 30.0), 1)
        ELSE 999
    END AS daysOfStock
FROM Product p
LEFT JOIN Inventory i ON i.productId = p.id
LEFT JOIN OrderItem oi ON oi.productId = p.id
LEFT JOIN "Order" o ON oi.orderId = o.id
    AND o.status != 'Cancelled'
    AND o.orderDate >= date('now', '-30 days')
GROUP BY p.id, p.sku, p.name, p.category, p.price, i.stockLevel
HAVING dailyVelocity > 0 AND daysOfStock < 30
ORDER BY daysOfStock ASC
LIMIT 50
""".strip(),
    },

    # ── Analytical Queries ──────────────────────────────────────────────────
    "sales_last_30d": {
        "description": "30-day sales summary: orders, revenue, AOV, compared to prior 30 days",
        "date_range_days": 30,
        "sql": """
WITH current_period AS (
    SELECT
        COUNT(*) AS orders,
        ROUND(SUM(totalAmount), 2) AS revenue,
        ROUND(AVG(totalAmount), 2) AS aov
    FROM "Order"
    WHERE status != 'Cancelled'
      AND orderDate >= date('now', '-30 days')
),
prior_period AS (
    SELECT
        COUNT(*) AS orders,
        ROUND(SUM(totalAmount), 2) AS revenue,
        ROUND(AVG(totalAmount), 2) AS aov
    FROM "Order"
    WHERE status != 'Cancelled'
      AND orderDate >= date('now', '-60 days')
      AND orderDate < date('now', '-30 days')
)
SELECT
    c.orders AS current_orders,
    c.revenue AS current_revenue,
    c.aov AS current_aov,
    p.orders AS prior_orders,
    p.revenue AS prior_revenue,
    p.aov AS prior_aov,
    CASE WHEN p.revenue > 0
        THEN ROUND((c.revenue - p.revenue) * 100.0 / p.revenue, 1)
        ELSE NULL
    END AS revenue_change_pct,
    CASE WHEN p.orders > 0
        THEN ROUND((c.orders - p.orders) * 100.0 / p.orders, 1)
        ELSE NULL
    END AS orders_change_pct
FROM current_period c, prior_period p
""".strip(),
    },
    "aov_by_month": {
        "description": "Average order value trend by month (last 12 months, excludes cancelled)",
        "date_range_days": 365,
        "sql": """
SELECT
    strftime('%Y-%m', orderDate) AS month,
    COUNT(*) AS orders,
    ROUND(SUM(totalAmount), 2) AS revenue,
    ROUND(AVG(totalAmount), 2) AS aov
FROM "Order"
WHERE status != 'Cancelled'
  AND orderDate >= date('now', '-12 months')
GROUP BY month
ORDER BY month ASC
""".strip(),
    },
    "revenue_share_by_category": {
        "description": "Category revenue as percentage of total (ALL TIME, delivered orders only — use revenue_by_category_30d for period-specific data)",
        "sql": """
SELECT
    p.category,
    COUNT(DISTINCT o.id) AS orders,
    SUM(oi.quantity) AS units_sold,
    ROUND(SUM(oi.quantity * oi.unitPrice), 2) AS revenue,
    ROUND(SUM(oi.quantity * oi.unitPrice) * 100.0 / SUM(SUM(oi.quantity * oi.unitPrice)) OVER(), 1) AS revenue_share_pct
FROM OrderItem oi
JOIN Product p ON oi.productId = p.id
JOIN "Order" o ON oi.orderId = o.id
WHERE o.status = 'Delivered'
GROUP BY p.category
ORDER BY revenue DESC
""".strip(),
    },
    "top_products_with_share": {
        "description": "Top 15 products with revenue and percentage share of total (excluding cancelled)",
        "sql": """
SELECT
    p.name,
    p.category,
    SUM(oi.quantity) AS units_sold,
    ROUND(SUM(oi.quantity * oi.unitPrice), 2) AS revenue,
    ROUND(SUM(oi.quantity * oi.unitPrice) * 100.0 / SUM(SUM(oi.quantity * oi.unitPrice)) OVER(), 1) AS revenue_share_pct
FROM OrderItem oi
JOIN Product p ON oi.productId = p.id
JOIN "Order" o ON oi.orderId = o.id
WHERE o.status != 'Cancelled'
GROUP BY p.id, p.name, p.category
ORDER BY revenue DESC
LIMIT 15
""".strip(),
    },
    "stockout_risk": {
        "description": "Products with less than 14 days of stock cover and positive sales velocity",
        "sql": """
SELECT
    p.name,
    p.category,
    ROUND(p.price, 2) AS price,
    COALESCE(i.stockLevel, 0) AS currentStock,
    COALESCE(SUM(oi.quantity), 0) AS unitsSold30d,
    ROUND(COALESCE(SUM(oi.quantity), 0) / 30.0, 2) AS dailyVelocity,
    ROUND(COALESCE(i.stockLevel, 0) / (COALESCE(SUM(oi.quantity), 0) / 30.0), 1) AS daysOfStock
FROM Product p
LEFT JOIN Inventory i ON i.productId = p.id
LEFT JOIN OrderItem oi ON oi.productId = p.id
LEFT JOIN "Order" o ON oi.orderId = o.id
    AND o.status != 'Cancelled'
    AND o.orderDate >= date('now', '-30 days')
GROUP BY p.id, p.name, p.category, p.price, i.stockLevel
HAVING COALESCE(SUM(oi.quantity), 0) > 0
    AND COALESCE(i.stockLevel, 0) / (COALESCE(SUM(oi.quantity), 0) / 30.0) < 14
ORDER BY daysOfStock ASC
""".strip(),
    },
    "high_rated_low_sales": {
        "description": "Products with average rating >= 4.0 but in the bottom 50% by revenue — hidden gems",
        "sql": """
WITH product_revenue AS (
    SELECT
        p.id,
        p.name,
        p.category,
        ROUND(p.price, 2) AS price,
        COALESCE(SUM(oi.quantity * oi.unitPrice), 0) AS revenue
    FROM Product p
    LEFT JOIN OrderItem oi ON oi.productId = p.id
    LEFT JOIN "Order" o ON oi.orderId = o.id AND o.status = 'Delivered'
    GROUP BY p.id, p.name, p.category, p.price
),
median_rev AS (
    SELECT revenue AS median_revenue
    FROM product_revenue
    WHERE revenue > 0
    ORDER BY revenue
    LIMIT 1 OFFSET (SELECT COUNT(*) / 2 FROM product_revenue WHERE revenue > 0)
)
SELECT
    pr.name,
    pr.category,
    pr.price,
    pr.revenue,
    ROUND(AVG(r.rating), 2) AS avg_rating,
    COUNT(r.id) AS review_count
FROM product_revenue pr
JOIN Review r ON r.productId = pr.id
CROSS JOIN median_rev m
GROUP BY pr.id, pr.name, pr.category, pr.price, pr.revenue
HAVING avg_rating >= 4.0 AND pr.revenue <= m.median_revenue
ORDER BY avg_rating DESC, pr.revenue ASC
""".strip(),
    },
    "customer_segments": {
        "description": "Customers segmented by spend tier: VIP (>$500), Regular ($200-$500), Occasional ($1-$200), New (no orders)",
        "sql": """
SELECT
    segment,
    COUNT(*) AS customer_count,
    ROUND(SUM(total_spent), 2) AS segment_revenue,
    ROUND(AVG(total_spent), 2) AS avg_spend,
    ROUND(SUM(total_spent) * 100.0 / NULLIF((SELECT SUM(totalAmount) FROM "Order" WHERE status != 'Cancelled'), 0), 1) AS revenue_share_pct
FROM (
    SELECT
        c.id,
        c.firstName || ' ' || c.lastName AS customer,
        COALESCE(SUM(o.totalAmount), 0) AS total_spent,
        CASE
            WHEN COALESCE(SUM(o.totalAmount), 0) > 500 THEN 'VIP'
            WHEN COALESCE(SUM(o.totalAmount), 0) > 200 THEN 'Regular'
            WHEN COALESCE(SUM(o.totalAmount), 0) > 0 THEN 'Occasional'
            ELSE 'New'
        END AS segment
    FROM Customer c
    LEFT JOIN "Order" o ON o.customerId = c.id AND o.status != 'Cancelled'
    GROUP BY c.id, c.firstName, c.lastName
)
GROUP BY segment
ORDER BY segment_revenue DESC
""".strip(),
    },
    "cancelled_order_rate": {
        "description": "Monthly cancellation rate as percentage of all orders",
        "date_range_days": 365,
        "sql": """
SELECT
    strftime('%Y-%m', orderDate) AS month,
    COUNT(*) AS total_orders,
    SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled,
    ROUND(SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS cancellation_rate_pct
FROM "Order"
WHERE orderDate >= date('now', '-12 months')
GROUP BY month
ORDER BY month ASC
""".strip(),
    },
    "reorder_with_cost": {
        "description": "Reorder candidates with suggested quantity and estimated PO cost per line item (only products needing reorder)",
        "date_range_days": 30,
        "sql": """
WITH reorder_data AS (
    SELECT
        p.sku,
        p.name,
        p.category,
        ROUND(p.price, 2) AS unitCost,
        COALESCE(i.stockLevel, 0) AS currentStock,
        ROUND(COALESCE(SUM(oi.quantity), 0) / 30.0, 2) AS dailyVelocity,
        ROUND(COALESCE(i.stockLevel, 0) / NULLIF(COALESCE(SUM(oi.quantity), 0) / 30.0, 0), 1) AS daysOfStock,
        MAX(0, CAST(CEIL(COALESCE(SUM(oi.quantity), 0) / 30.0 * 30) - COALESCE(i.stockLevel, 0) AS INTEGER)) AS suggestedQty,
        ROUND(MAX(0, CEIL(COALESCE(SUM(oi.quantity), 0) / 30.0 * 30) - COALESCE(i.stockLevel, 0)) * p.price, 2) AS lineCost
    FROM Product p
    LEFT JOIN Inventory i ON i.productId = p.id
    LEFT JOIN OrderItem oi ON oi.productId = p.id
    LEFT JOIN "Order" o ON oi.orderId = o.id
        AND o.status != 'Cancelled'
        AND o.orderDate >= date('now', '-30 days')
    GROUP BY p.id, p.sku, p.name, p.category, p.price, i.stockLevel
    HAVING COALESCE(SUM(oi.quantity), 0) > 0
        AND COALESCE(i.stockLevel, 0) / NULLIF(COALESCE(SUM(oi.quantity), 0) / 30.0, 0) < 30
)
SELECT * FROM reorder_data
WHERE suggestedQty > 0
ORDER BY daysOfStock ASC
""".strip(),
    },

    # ── New Period-Specific Queries ─────────────────────────────────────────
    "sales_last_7d": {
        "description": "7-day sales summary: orders, revenue, AOV, compared to prior 7 days",
        "date_range_days": 7,
        "sql": """
WITH current_period AS (
    SELECT COUNT(*) AS orders, ROUND(SUM(totalAmount), 2) AS revenue, ROUND(AVG(totalAmount), 2) AS aov
    FROM "Order" WHERE status != 'Cancelled' AND orderDate >= date('now', '-7 days')
),
prior_period AS (
    SELECT COUNT(*) AS orders, ROUND(SUM(totalAmount), 2) AS revenue, ROUND(AVG(totalAmount), 2) AS aov
    FROM "Order" WHERE status != 'Cancelled' AND orderDate >= date('now', '-14 days') AND orderDate < date('now', '-7 days')
)
SELECT c.orders AS current_orders, c.revenue AS current_revenue, c.aov AS current_aov,
    p.orders AS prior_orders, p.revenue AS prior_revenue, p.aov AS prior_aov,
    CASE WHEN p.revenue > 0 THEN ROUND((c.revenue - p.revenue) * 100.0 / p.revenue, 1) ELSE NULL END AS revenue_change_pct,
    CASE WHEN p.orders > 0 THEN ROUND((c.orders - p.orders) * 100.0 / p.orders, 1) ELSE NULL END AS orders_change_pct
FROM current_period c, prior_period p
""".strip(),
    },
    "sales_last_90d": {
        "description": "90-day sales summary: orders, revenue, AOV, compared to prior 90 days",
        "date_range_days": 90,
        "sql": """
WITH current_period AS (
    SELECT COUNT(*) AS orders, ROUND(SUM(totalAmount), 2) AS revenue, ROUND(AVG(totalAmount), 2) AS aov
    FROM "Order" WHERE status != 'Cancelled' AND orderDate >= date('now', '-90 days')
),
prior_period AS (
    SELECT COUNT(*) AS orders, ROUND(SUM(totalAmount), 2) AS revenue, ROUND(AVG(totalAmount), 2) AS aov
    FROM "Order" WHERE status != 'Cancelled' AND orderDate >= date('now', '-180 days') AND orderDate < date('now', '-90 days')
)
SELECT c.orders AS current_orders, c.revenue AS current_revenue, c.aov AS current_aov,
    p.orders AS prior_orders, p.revenue AS prior_revenue, p.aov AS prior_aov,
    CASE WHEN p.revenue > 0 THEN ROUND((c.revenue - p.revenue) * 100.0 / p.revenue, 1) ELSE NULL END AS revenue_change_pct,
    CASE WHEN p.orders > 0 THEN ROUND((c.orders - p.orders) * 100.0 / p.orders, 1) ELSE NULL END AS orders_change_pct
FROM current_period c, prior_period p
""".strip(),
    },
    "revenue_by_category_30d": {
        "description": "Category revenue with % share for the last 30 days (excluding cancelled)",
        "date_range_days": 30,
        "sql": """
SELECT
    p.category,
    COUNT(DISTINCT o.id) AS orders,
    SUM(oi.quantity) AS units_sold,
    ROUND(SUM(oi.quantity * oi.unitPrice), 2) AS revenue,
    ROUND(SUM(oi.quantity * oi.unitPrice) * 100.0 / SUM(SUM(oi.quantity * oi.unitPrice)) OVER(), 1) AS revenue_share_pct
FROM OrderItem oi
JOIN Product p ON oi.productId = p.id
JOIN "Order" o ON oi.orderId = o.id
WHERE o.status != 'Cancelled'
  AND o.orderDate >= date('now', '-30 days')
GROUP BY p.category
ORDER BY revenue DESC
""".strip(),
    },
    "revenue_by_category_90d": {
        "description": "Category revenue with % share for the last 90 days (excluding cancelled)",
        "date_range_days": 90,
        "sql": """
SELECT
    p.category,
    COUNT(DISTINCT o.id) AS orders,
    SUM(oi.quantity) AS units_sold,
    ROUND(SUM(oi.quantity * oi.unitPrice), 2) AS revenue,
    ROUND(SUM(oi.quantity * oi.unitPrice) * 100.0 / SUM(SUM(oi.quantity * oi.unitPrice)) OVER(), 1) AS revenue_share_pct
FROM OrderItem oi
JOIN Product p ON oi.productId = p.id
JOIN "Order" o ON oi.orderId = o.id
WHERE o.status != 'Cancelled'
  AND o.orderDate >= date('now', '-90 days')
GROUP BY p.category
ORDER BY revenue DESC
""".strip(),
    },

    # ── Prospecting Queries ─────────────────────────────────────────────────
    "business_health_snapshot": {
        "description": "Single-row business snapshot: total revenue, orders, avg rating, stockout count, top/worst category",
        "sql": """
WITH revenue AS (
    SELECT
        COUNT(*) AS total_orders,
        ROUND(SUM(totalAmount), 2) AS total_revenue,
        ROUND(AVG(totalAmount), 2) AS avg_order_value
    FROM "Order"
    WHERE status != 'Cancelled'
),
ratings AS (
    SELECT ROUND(AVG(rating), 2) AS avg_rating, COUNT(*) AS total_reviews
    FROM Review
),
stockouts AS (
    SELECT COUNT(*) AS stockout_count
    FROM Inventory WHERE stockLevel = 0
),
top_cat AS (
    SELECT p.category AS top_category
    FROM OrderItem oi
    JOIN Product p ON oi.productId = p.id
    JOIN "Order" o ON oi.orderId = o.id
    WHERE o.status != 'Cancelled'
    GROUP BY p.category
    ORDER BY SUM(oi.quantity * oi.unitPrice) DESC
    LIMIT 1
),
worst_cat AS (
    SELECT p.category AS worst_category
    FROM OrderItem oi
    JOIN Product p ON oi.productId = p.id
    JOIN "Order" o ON oi.orderId = o.id
    WHERE o.status != 'Cancelled'
    GROUP BY p.category
    ORDER BY SUM(oi.quantity * oi.unitPrice) ASC
    LIMIT 1
)
SELECT
    r.total_orders, r.total_revenue, r.avg_order_value,
    rt.avg_rating, rt.total_reviews,
    s.stockout_count,
    tc.top_category, wc.worst_category
FROM revenue r, ratings rt, stockouts s, top_cat tc, worst_cat wc
""".strip(),
    },
    "opportunity_matrix": {
        "description": "Products with high rating (>=4.0) + low revenue + high stock — automation opportunities",
        "sql": """
SELECT
    p.name,
    p.category,
    ROUND(p.price, 2) AS price,
    COALESCE(i.stockLevel, 0) AS stock,
    ROUND(AVG(rv.rating), 2) AS avg_rating,
    COUNT(rv.id) AS reviews,
    COALESCE(ROUND(SUM(oi.quantity * oi.unitPrice), 2), 0) AS revenue
FROM Product p
LEFT JOIN Inventory i ON i.productId = p.id
LEFT JOIN Review rv ON rv.productId = p.id
LEFT JOIN OrderItem oi ON oi.productId = p.id
LEFT JOIN "Order" o ON oi.orderId = o.id AND o.status != 'Cancelled'
GROUP BY p.id, p.name, p.category, p.price, i.stockLevel
HAVING avg_rating >= 4.0 AND revenue < (
    SELECT AVG(rev) FROM (
        SELECT COALESCE(SUM(oi2.quantity * oi2.unitPrice), 0) AS rev
        FROM Product p2
        LEFT JOIN OrderItem oi2 ON oi2.productId = p2.id
        LEFT JOIN "Order" o2 ON oi2.orderId = o2.id AND o2.status != 'Cancelled'
        GROUP BY p2.id
    )
)
ORDER BY avg_rating DESC, stock DESC
LIMIT 15
""".strip(),
    },
    "automation_candidates": {
        "description": "Counts of repetitive patterns: pending orders, stockout-risk products, inactive customers — quantifies automation potential",
        "sql": """
WITH pending AS (
    SELECT COUNT(*) AS pending_orders FROM "Order" WHERE status = 'Pending'
),
stockout_risk AS (
    SELECT COUNT(*) AS at_risk_products
    FROM (
        SELECT p.id,
            COALESCE(i.stockLevel, 0) AS stock,
            COALESCE(SUM(oi.quantity), 0) AS sold30d
        FROM Product p
        LEFT JOIN Inventory i ON i.productId = p.id
        LEFT JOIN OrderItem oi ON oi.productId = p.id
        LEFT JOIN "Order" o ON oi.orderId = o.id
            AND o.status != 'Cancelled'
            AND o.orderDate >= date('now', '-30 days')
        GROUP BY p.id, i.stockLevel
        HAVING sold30d > 0
            AND COALESCE(i.stockLevel, 0) / (COALESCE(SUM(oi.quantity), 0) / 30.0) < 14
    )
),
inactive AS (
    SELECT COUNT(*) AS inactive_customers
    FROM Customer c
    WHERE c.id NOT IN (
        SELECT DISTINCT customerId FROM "Order"
        WHERE orderDate >= date('now', '-90 days')
    )
),
low_rated AS (
    SELECT COUNT(DISTINCT productId) AS low_rated_products
    FROM Review
    GROUP BY productId
    HAVING AVG(rating) < 3.0
)
SELECT
    p.pending_orders,
    s.at_risk_products,
    i.inactive_customers,
    COALESCE(lr.low_rated_products, 0) AS low_rated_products
FROM pending p, stockout_risk s, inactive i,
    (SELECT COUNT(*) AS low_rated_products FROM (
        SELECT productId FROM Review GROUP BY productId HAVING AVG(rating) < 3.0
    )) lr
""".strip(),
    },
}
