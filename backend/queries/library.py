# Pre-built SQL queries for the e-commerce database.
# Keys are the query names the agent uses. Values are ready-to-run SELECT statements.
# Add new entries here to expand coverage without touching the tool code.

QUERY_LIBRARY: dict[str, dict] = {

    # ── Sales & Revenue ──────────────────────────────────────────────────────
    "total_revenue": {
        "description": "Total revenue across all delivered orders",
        "sql": """
SELECT
    COUNT(*) AS total_orders,
    ROUND(SUM(totalAmount), 2) AS total_revenue,
    ROUND(AVG(totalAmount), 2) AS avg_order_value
FROM "Order"
WHERE status = 'Delivered'
""".strip(),
    },
    "revenue_by_month": {
        "description": "Monthly revenue for delivered orders (last 12 months)",
        "sql": """
SELECT
    strftime('%Y-%m', orderDate) AS month,
    COUNT(*) AS orders,
    ROUND(SUM(totalAmount), 2) AS revenue
FROM "Order"
WHERE status = 'Delivered'
  AND orderDate >= date('now', '-12 months')
GROUP BY month
ORDER BY month DESC
""".strip(),
    },
    "revenue_by_category": {
        "description": "Total revenue broken down by product category",
        "sql": """
SELECT
    p.category,
    COUNT(DISTINCT o.id) AS orders,
    SUM(oi.quantity) AS units_sold,
    ROUND(SUM(oi.quantity * oi.unitPrice), 2) AS revenue
FROM OrderItem oi
JOIN Product p ON oi.productId = p.id
JOIN "Order" o ON oi.orderId = o.id
WHERE o.status = 'Delivered'
GROUP BY p.category
ORDER BY revenue DESC
""".strip(),
    },

    # ── Products ─────────────────────────────────────────────────────────────
    "top_products_by_revenue": {
        "description": "Top 10 products ranked by total revenue",
        "sql": """
SELECT
    p.name,
    p.category,
    SUM(oi.quantity) AS units_sold,
    ROUND(SUM(oi.quantity * oi.unitPrice), 2) AS revenue
FROM OrderItem oi
JOIN Product p ON oi.productId = p.id
JOIN "Order" o ON oi.orderId = o.id
WHERE o.status = 'Delivered'
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
        "description": "Products with stock level below 10 units",
        "sql": """
SELECT
    p.name,
    p.category,
    i.stockLevel,
    i.lastRestock
FROM Inventory i
JOIN Product p ON i.productId = p.id
WHERE i.stockLevel < 10
ORDER BY i.stockLevel ASC
""".strip(),
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
    o.orderDate,
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
    o.orderDate,
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
    o.orderDate,
    ROUND(o.totalAmount, 2) AS amount
FROM "Order" o
JOIN Customer c ON o.customerId = c.id
WHERE o.status = 'Pending'
ORDER BY o.orderDate ASC
""".strip(),
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
    createdAt
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
    r.createdAt
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
    po.createdAt
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
}
