import json
import uuid
from datetime import datetime

from langchain_core.runnables import ensure_config
from langchain_core.tools import tool

from ..config import DB_PATH
from ..db import get_connection
from ..hitl_state import has_po_intent, is_approved

# Actions that modify the database — require HITL approval
_WRITE_ACTIONS = {"create_po", "approve_po", "receive_po"}


@tool
def purchase_order_action(action: str, data: str = "{}") -> str:
    """Manage supplier purchase orders. This tool can create, approve, and receive POs,
    and also list suppliers. Use this after HITL approval for replenishment workflows.

    Actions:
      - "list_suppliers": List all available suppliers. No data needed.
      - "create_po": Create a draft purchase order.
        data = JSON: {"supplierId": "...", "items": [{"productId": "...", "sku": "...", "name": "...", "quantity": 10, "unitCost": 5.99}], "auto_receive_on_approve": true}
      - "approve_po": Approve a draft PO. data = JSON: {"po_id": "...", "auto_receive": true}
      - "receive_po": Mark an approved PO as received and update inventory. data = JSON: {"po_id": "..."}
      - "get_po": Get details of a purchase order. data = JSON: {"po_id": "..."}
      - "list_pos": List all purchase orders. No data needed.
    """
    try:
        params = json.loads(data) if data else {}
    except json.JSONDecodeError:
        return "Error: invalid JSON in data parameter."

    # ── Code-level intent guard ─────────────────────────────────────────
    # Block ALL purchase_order_action calls if the user never asked for PO work.
    # This prevents the LLM from hallucinating PO workflows during unrelated tasks.
    try:
        config = ensure_config()
        thread_id = config.get("configurable", {}).get("thread_id", "")
    except Exception:
        thread_id = ""

    if not has_po_intent(thread_id):
        return (
            "Error: The user has not requested any purchase order or replenishment work. "
            "Do NOT call purchase_order_action unless the user explicitly asks for "
            "replenishment, restocking, or purchase orders. "
            "Continue with the current task instead."
        )

    # ── Code-level HITL enforcement ──────────────────────────────────────
    if action in _WRITE_ACTIONS:
        if not is_approved(thread_id):
            return (
                "Error: This action requires human approval. "
                "You must first output a HITL_REQUEST JSON block and wait for "
                "the user to click Approve before calling create_po, approve_po, "
                "or receive_po."
            )

    try:
        with get_connection() as conn:
            if action == "list_suppliers":
                rows = conn.execute(
                    "SELECT id, name, email, phone FROM Supplier ORDER BY name"
                ).fetchall()
                if not rows:
                    return "No suppliers found."
                lines = ["| Name | Email | Phone | ID |", "| --- | --- | --- | --- |"]
                for r in rows:
                    lines.append(f"| {r['name']} | {r['email'] or '-'} | {r['phone'] or '-'} | {r['id']} |")
                return "\n".join(lines)

            elif action == "create_po":
                supplier_id = params.get("supplierId")
                items = params.get("items", [])
                auto_receive = params.get("auto_receive_on_approve", False)

                if not supplier_id or not items:
                    return "Error: supplierId and items are required."

                # Validate supplier
                supplier = conn.execute(
                    "SELECT id, name FROM Supplier WHERE id = ?", (supplier_id,)
                ).fetchone()
                if not supplier:
                    return f"Error: Supplier '{supplier_id}' not found."

                po_id = str(uuid.uuid4())
                total = round(sum(i["quantity"] * i["unitCost"] for i in items), 2)

                conn.execute(
                    "INSERT INTO PurchaseOrder (id, supplierId, createdAt, status, totalAmount) VALUES (?, ?, ?, 'Draft', ?)",
                    (po_id, supplier_id, datetime.utcnow().isoformat(), total),
                )

                for item in items:
                    # Auto-resolve productId from SKU or name if not provided
                    product_id = item.get("productId")
                    if not product_id:
                        sku = item.get("sku", "")
                        name = item.get("name", "")
                        if sku:
                            row = conn.execute("SELECT id FROM Product WHERE sku = ?", (sku,)).fetchone()
                            if row:
                                product_id = row["id"]
                        if not product_id and name:
                            row = conn.execute("SELECT id FROM Product WHERE name = ?", (name,)).fetchone()
                            if row:
                                product_id = row["id"]

                    conn.execute(
                        "INSERT INTO PurchaseOrderItem (id, purchaseOrderId, productId, sku, name, quantity, unitCost) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(uuid.uuid4()),
                            po_id,
                            product_id,
                            item.get("sku"),
                            item.get("name"),
                            item["quantity"],
                            item["unitCost"],
                        ),
                    )

                # Auto approve+receive if requested
                if auto_receive:
                    conn.execute("UPDATE PurchaseOrder SET status = 'Approved' WHERE id = ?", (po_id,))
                    changes = _receive_po_impl(conn, po_id)
                    conn.commit()
                    return _format_po_result(conn, po_id, supplier["name"], changes)
                else:
                    conn.commit()
                    return f"Purchase order created (Draft). PO ID: {po_id}\nSupplier: {supplier['name']}\nTotal: ${total}\nItems: {len(items)}"

            elif action == "approve_po":
                po_id = params.get("po_id")
                auto_receive = params.get("auto_receive", False)
                if not po_id:
                    return "Error: po_id is required."

                po = conn.execute("SELECT id, status FROM PurchaseOrder WHERE id = ?", (po_id,)).fetchone()
                if not po:
                    return f"Error: PO '{po_id}' not found."
                if po["status"] != "Draft":
                    return f"Error: Cannot approve PO with status '{po['status']}'."

                conn.execute("UPDATE PurchaseOrder SET status = 'Approved' WHERE id = ?", (po_id,))

                if auto_receive:
                    changes = _receive_po_impl(conn, po_id)
                    conn.commit()
                    supplier_name = conn.execute(
                        "SELECT s.name FROM PurchaseOrder po JOIN Supplier s ON po.supplierId = s.id WHERE po.id = ?",
                        (po_id,),
                    ).fetchone()["name"]
                    return _format_po_result(conn, po_id, supplier_name, changes)
                else:
                    conn.commit()
                    return f"PO {po_id} approved successfully."

            elif action == "receive_po":
                po_id = params.get("po_id")
                if not po_id:
                    return "Error: po_id is required."

                po = conn.execute("SELECT id, status FROM PurchaseOrder WHERE id = ?", (po_id,)).fetchone()
                if not po:
                    return f"Error: PO '{po_id}' not found."
                if po["status"] == "Received":
                    return f"PO {po_id} was already received. No duplicate stock changes applied."
                if po["status"] not in ("Approved", "Sent"):
                    return f"Error: Cannot receive PO with status '{po['status']}'."

                changes = _receive_po_impl(conn, po_id)
                conn.commit()
                supplier_name = conn.execute(
                    "SELECT s.name FROM PurchaseOrder po JOIN Supplier s ON po.supplierId = s.id WHERE po.id = ?",
                    (po_id,),
                ).fetchone()["name"]
                return _format_po_result(conn, po_id, supplier_name, changes)

            elif action == "get_po":
                po_id = params.get("po_id")
                if not po_id:
                    return "Error: po_id is required."
                po = conn.execute(
                    "SELECT po.id, s.name AS supplierName, po.createdAt, po.status, po.totalAmount FROM PurchaseOrder po JOIN Supplier s ON po.supplierId = s.id WHERE po.id = ?",
                    (po_id,),
                ).fetchone()
                if not po:
                    return f"Error: PO '{po_id}' not found."
                items = conn.execute(
                    "SELECT sku, name, quantity, unitCost, ROUND(quantity * unitCost, 2) AS lineTotal FROM PurchaseOrderItem WHERE purchaseOrderId = ?",
                    (po_id,),
                ).fetchall()
                lines = [
                    f"**PO {po['id'][:8]}...** | Supplier: {po['supplierName']} | Status: {po['status']} | Total: ${po['totalAmount']}",
                    "",
                    "| SKU | Name | Qty | Unit Cost | Line Total |",
                    "| --- | --- | --- | --- | --- |",
                ]
                for it in items:
                    lines.append(f"| {it['sku']} | {it['name'] or '-'} | {it['quantity']} | ${it['unitCost']} | ${it['lineTotal']} |")
                return "\n".join(lines)

            elif action == "list_pos":
                rows = conn.execute(
                    "SELECT po.id, s.name AS supplierName, po.createdAt, po.status, po.totalAmount FROM PurchaseOrder po JOIN Supplier s ON po.supplierId = s.id ORDER BY po.createdAt DESC"
                ).fetchall()
                if not rows:
                    return "No purchase orders found."
                lines = ["| PO ID | Supplier | Status | Total | Created |", "| --- | --- | --- | --- | --- |"]
                for r in rows:
                    lines.append(f"| {r['id'][:8]}... | {r['supplierName']} | {r['status']} | ${r['totalAmount']} | {r['createdAt']} |")
                return "\n".join(lines)

            else:
                return f"Error: Unknown action '{action}'. Use: list_suppliers, create_po, approve_po, receive_po, get_po, list_pos."

    except Exception as exc:
        return f"Error: {exc}"


def _receive_po_impl(conn, po_id: str) -> list[dict]:
    """Receive PO: update inventory, create products if needed. Returns inventory changes."""
    items = conn.execute(
        "SELECT id, productId, sku, name, quantity, unitCost FROM PurchaseOrderItem WHERE purchaseOrderId = ?",
        (po_id,),
    ).fetchall()

    now = datetime.utcnow().isoformat()
    changes = []

    for item in items:
        product_id = item["productId"]

        if product_id is None:
            # Try to find existing product by SKU or name before creating a new one
            if item["sku"]:
                row = conn.execute("SELECT id FROM Product WHERE sku = ?", (item["sku"],)).fetchone()
                if row:
                    product_id = row["id"]
            if product_id is None and item["name"]:
                row = conn.execute("SELECT id FROM Product WHERE name = ?", (item["name"],)).fetchone()
                if row:
                    product_id = row["id"]
            if product_id is not None:
                conn.execute("UPDATE PurchaseOrderItem SET productId = ? WHERE id = ?", (product_id, item["id"]))
            else:
                # Create new product only when truly not found
                product_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO Product (id, name, description, price, category, sku) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        product_id,
                        item["name"] or f"New Product ({item['sku']})",
                        "Auto-created from purchase order",
                        item["unitCost"],
                        "Uncategorized",
                        item["sku"],
                    ),
                )
                conn.execute(
                    "UPDATE PurchaseOrderItem SET productId = ? WHERE id = ?",
                    (product_id, item["id"]),
                )

        inv = conn.execute(
            "SELECT id, stockLevel FROM Inventory WHERE productId = ?", (product_id,)
        ).fetchone()

        if inv:
            before = inv["stockLevel"]
            after = before + item["quantity"]
            conn.execute(
                "UPDATE Inventory SET stockLevel = ?, lastRestock = ? WHERE id = ?",
                (after, now, inv["id"]),
            )
        else:
            before = 0
            after = item["quantity"]
            conn.execute(
                "INSERT INTO Inventory (id, productId, stockLevel, lastRestock) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), product_id, after, now),
            )

        changes.append({
            "sku": item["sku"],
            "name": item["name"],
            "before": before,
            "after": after,
            "added": item["quantity"],
        })

    conn.execute("UPDATE PurchaseOrder SET status = 'Received' WHERE id = ?", (po_id,))
    return changes


def _format_po_result(conn, po_id: str, supplier_name: str, changes: list[dict]) -> str:
    po = conn.execute(
        "SELECT id, status, totalAmount FROM PurchaseOrder WHERE id = ?", (po_id,)
    ).fetchone()

    lines = [
        f"**Purchase Order {po_id[:8]}...** — Status: **{po['status']}** | Supplier: {supplier_name} | Total: ${po['totalAmount']}",
        "",
        "### Inventory Changes",
        "| SKU | Name | Stock Before | Stock After | Added |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in changes:
        lines.append(f"| {c['sku']} | {c['name'] or '-'} | {c['before']} | {c['after']} | +{c['added']} |")

    return "\n".join(lines)
