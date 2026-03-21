"""Lightweight programmatic validators for AgenticStack agent responses.

These run AFTER the full response is assembled, BEFORE persistence.
They append footnotes or warnings — they never modify the core content.
"""

import json
import re
from typing import Optional


def _extract_dollar_amounts(text: str) -> list[float]:
    """Extract dollar amounts from text, returning as floats."""
    matches = re.findall(r"\$[\d,]+\.?\d*", text)
    amounts = []
    for m in matches:
        try:
            amounts.append(float(m.replace("$", "").replace(",", "")))
        except ValueError:
            continue
    return amounts


def check_summary_breakdown_coherence(response: str) -> Optional[str]:
    """Check if a stated total in the summary matches the table breakdown.

    Returns a footnote string if a mismatch is detected, None otherwise.
    """
    lines = response.split("\n")

    # Find the first non-empty, non-header line (the summary area = first 5 non-empty lines)
    summary_lines = []
    table_lines = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect markdown table rows
        if "|" in stripped and not stripped.startswith("#"):
            if "---" in stripped:
                in_table = True
                continue
            if in_table:
                table_lines.append(stripped)
                continue

        if not in_table and len(summary_lines) < 5:
            summary_lines.append(stripped)

    if not summary_lines or not table_lines:
        return None

    # Extract dollar amounts from summary (looking for "total" context)
    summary_text = " ".join(summary_lines)
    summary_amounts = _extract_dollar_amounts(summary_text)

    # Extract dollar amounts from all table data rows
    table_text = " ".join(table_lines)
    table_amounts = _extract_dollar_amounts(table_text)

    if not summary_amounts or not table_amounts:
        return None

    # Find the largest summary amount (likely the "total")
    summary_total = max(summary_amounts)

    # Sum the table amounts (heuristic: sum the last dollar column)
    # This is approximate — we check for >10% deviation
    table_sum = sum(table_amounts)

    if table_sum == 0:
        return None

    deviation = abs(summary_total - table_sum) / table_sum
    if deviation > 0.10:
        return (
            "\n\n> *Note: The summary total and breakdown rows may reflect different "
            "query scopes or rounding. Verify figures against the SQL results tab.*"
        )

    # Check for dollar amounts near "total"/"sum"/"combined" that don't match any table amount
    total_context = re.findall(
        r"(?:total|sum|combined|grand\s*total)[^$\n]{0,30}\$([\d,]+\.?\d*)", summary_text, re.IGNORECASE
    )
    for match in total_context:
        try:
            stated = float(match.replace(",", ""))
        except ValueError:
            continue
        # Check if this amount appears in the table data (within 1% tolerance)
        found_match = any(abs(stated - ta) / max(ta, 0.01) < 0.01 for ta in table_amounts)
        if not found_match and stated > 0:
            return (
                "\n\n> *Note: A stated total may not match the breakdown data. "
                "Verify figures against the SQL results tab.*"
            )

    return None


def validate_hitl_structure(response: str) -> list[str]:
    """Validate HITL_REQUEST JSON blocks for required fields.

    Returns a list of warning strings (empty if valid).
    """
    warnings = []

    # Find ```json blocks containing HITL_REQUEST
    json_blocks = re.findall(r"```json\s*\n(.*?)```", response, re.DOTALL)
    if not json_blocks:
        return warnings

    for block in json_blocks:
        try:
            parsed = json.loads(block.strip())
        except json.JSONDecodeError:
            continue

        hitl = parsed.get("HITL_REQUEST")
        if not hitl:
            continue

        # Check required fields
        if not hitl.get("summary"):
            warnings.append("[CRITICAL] HITL_REQUEST is missing 'summary'")
        if not hitl.get("evidence") or len(hitl.get("evidence", [])) == 0:
            warnings.append("[CRITICAL] HITL_REQUEST has no evidence items")
        if not hitl.get("artifacts_preview") or len(hitl.get("artifacts_preview", [])) == 0:
            warnings.append("[CRITICAL] HITL_REQUEST has no artifacts_preview")
        if not hitl.get("controls") or len(hitl.get("controls", [])) == 0:
            warnings.append("HITL_REQUEST has no controls")
        if not hitl.get("actions") or len(hitl.get("actions", [])) < 2:
            warnings.append("[CRITICAL] HITL_REQUEST has fewer than 2 actions (need at least approve + reject)")
        if not hitl.get("risk_tags") or len(hitl.get("risk_tags", [])) == 0:
            warnings.append("[CRITICAL] HITL_REQUEST has no risk_tags")

        # For PO drafts: check non-zero quantities
        for artifact in hitl.get("artifacts_preview", []):
            atype = artifact.get("type", "")
            content = artifact.get("content", "")

            if atype in ("REPLENISHMENT_TABLE", "PURCHASE_ORDER_DRAFT"):
                # Check for grand total mention
                if "grand total" not in content.lower() and "total" not in content.lower():
                    warnings.append(f"{atype} artifact is missing a grand total line")

                # Check for all-zero quantities
                qty_matches = re.findall(r"\|\s*0\s*\|", content)
                non_zero_qty = re.findall(r"\|\s*[1-9]\d*\s*\|", content)
                if qty_matches and not non_zero_qty:
                    warnings.append(f"{atype} artifact appears to have all-zero quantities")

    return warnings


def normalize_empty_po_hitl_response(response: str) -> Optional[str]:
    """Convert an empty no-replenishment HITL card into a plain response."""
    json_blocks = re.findall(r"```json\s*\n(.*?)```", response, re.DOTALL)
    for block in json_blocks:
        try:
            parsed = json.loads(block.strip())
        except json.JSONDecodeError:
            continue

        hitl = parsed.get("HITL_REQUEST")
        if not hitl:
            continue

        title = str(hitl.get("title", ""))
        summary = str(hitl.get("summary", ""))
        blob = f"{title} {summary}".lower()
        is_po = any(term in blob for term in ("purchase order", "replenishment", "restock", "reorder"))
        no_reorder = any(
            phrase in blob
            for phrase in (
                "sufficient stock",
                "no products are currently at stockout risk",
                "no reorder",
                "no replenishment",
            )
        )
        empty_card = not hitl.get("evidence") and not hitl.get("artifacts_preview") and not hitl.get("controls") and not hitl.get("actions")

        if is_po and no_reorder and empty_card:
            return (
                "### Replenishment Status\n\n"
                "All products have sufficient stock. No replenishment or purchase order is needed right now."
            )

    return None


def check_response_length(response: str, mode_name: str) -> Optional[str]:
    """Check if response exceeds recommended length for its mode.

    Returns a warning string if too long, None otherwise.
    This is for logging/eval only — not appended to the response.
    """
    max_chars = {
        "factual": 1500,
        "analytical": 3000,
        "chart": 2000,
        "hitl": 5000,
        "rag": 1200,
        "web": 2000,
        "prospecting": 3500,
    }

    limit = max_chars.get(mode_name, 3000)
    if len(response) > limit:
        return f"Response length ({len(response)} chars) exceeds {mode_name} mode limit ({limit} chars)"

    return None
