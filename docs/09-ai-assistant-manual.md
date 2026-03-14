# AI Assistant Manual

## Overview

This document describes the capabilities, limitations, escalation logic, and interaction design of the platform's AI-powered assistant. It serves as internal documentation for the RAG system and as a reference for developers and support teams integrating AI features.

---

## Assistant Identity

**Name:** Aria (Adaptive Retail Intelligence Assistant)
**Powered by:** Large Language Model with RAG (Retrieval-Augmented Generation)
**Primary Interface:** Chat widget (web + mobile), email response drafting
**Languages supported:** English (primary), French, Spanish (beta)

---

## What the AI Assistant Can Do

### Product Discovery
- Answer natural language product search queries
  - *"I need a gift for a 10-year-old who loves science"*
  - *"What's the best keyboard for a programmer who works at night?"*
- Recommend products based on stated preferences, budget, and use case
- Compare products side by side on request
- Explain technical specifications in plain language
- Surface bundles and promotions relevant to the query

### Order Support
- Retrieve order status by email + order ID verification
- Explain what each order status means (Pending, Shipped, Delivered, Cancelled)
- Provide estimated delivery windows based on shipping method
- Guide customers through the return initiation process step-by-step
- Confirm whether a cancellation is still possible

### Policy & Information
- Answer questions about shipping, returns, refunds, and payments
- Explain promo code rules and discount eligibility
- Describe the review and rating system
- Clarify loyalty program tiers and point redemption

### Personalization
- Remember preferences within a session (not across sessions by default)
- Adjust recommendations based on stated skin type, fitness level, or dietary needs
- Surface "customers also bought" suggestions contextually

---

## What the AI Assistant Cannot Do

The assistant **will not** perform the following actions — these require either the account portal or a human agent:

| Action | Reason | Escalation Path |
|---|---|---|
| Process a refund | Requires financial system access | Human support |
| Cancel an order | Account authentication required | Account portal or human |
| Modify a shipping address | Security-sensitive | Account portal (Pending only) |
| Change payment method on existing order | PCI compliance | Human support |
| Delete customer account | Irreversible action | Human support |
| Access full credit card information | Never stored | N/A |
| Apply a promo code retroactively | System limitation | Human support (case-by-case) |

---

## Knowledge Base & RAG Architecture

### Data Sources
The assistant is grounded in the following real-time and static sources:

| Source | Update Frequency | Content |
|---|---|---|
| Product catalog (database) | Real-time | Names, descriptions, prices, stock |
| Policy documents (docs/) | On update | Shipping, returns, FAQ, promos |
| Review data (database) | Real-time | Ratings, sentiment, keywords |
| Inventory levels | Real-time | Stock availability |
| Order data | Real-time (per session) | Order status, history |

### Retrieval Logic
1. Customer message is embedded into a vector
2. Top-K most relevant documents/records are retrieved
3. Retrieved context is injected into the prompt
4. Model generates a grounded, accurate response
5. Response includes confidence signals and source attribution when relevant

### Hallucination Prevention
- All product-specific claims are grounded in the product catalog
- If no relevant product is found, the assistant says so rather than inventing one
- Price and stock information is always fetched live, never generated
- Out-of-scope queries return a graceful "I don't know" + escalation offer

---

## Escalation Logic

### Automatic Escalation Triggers
The AI hands off to a human agent when:
1. Customer expresses frustration **3+ times** in the same session
2. Query requires account-level action (refund, cancellation)
3. Complaint involves a defective product or safety concern
4. Legal or regulatory language is detected in the message
5. Customer explicitly asks to speak with a human

### Escalation Handoff Message
```
"I understand this requires more direct assistance. I'm connecting you
with a member of our support team. Your conversation history will be
shared so you won't need to repeat yourself. Expected wait time: [X] minutes."
```

### Escalation Channels
- **Live chat** — during business hours (Mon–Fri 8AM–8PM EST)
- **Email ticket** — auto-created with conversation transcript attached
- **Callback request** — for high-priority/Platinum tier customers

---

## Conversation Design Principles

### Tone
- Friendly and professional — not robotic, not overly casual
- Use customer's name when available
- Acknowledge frustration before moving to solutions
- Short sentences. No jargon without explanation.

### Response Length Guidelines
| Query Type | Target Length |
|---|---|
| Simple factual (order status, policy) | 1–3 sentences |
| Product recommendation | 3–5 sentences + product list |
| Complex (comparison, troubleshooting) | Structured response with headers |
| Escalation | 2–3 sentences + next step |

### What to Avoid
- Do not apologize excessively ("I'm so sorry, I deeply apologize...")
- Do not use filler phrases ("Great question!", "Certainly!", "Absolutely!")
- Do not hallucinate product features, prices, or policies
- Do not make promises that require human approval (e.g., "I'll make sure you get a refund")

---

## Privacy & Data Handling

### What the AI Accesses
- Product catalog (public data)
- Order data — only after identity verification (email + order ID)
- Review text (aggregated, anonymized for training)
- Session conversation history (cleared after session ends)

### What the AI Never Accesses
- Full payment card details
- Passwords or authentication tokens
- Other customers' personal data
- Internal financial transaction records

### Data Retention
- Session data: deleted after 30 minutes of inactivity
- Conversation logs: retained for 90 days for quality review
- No conversation data is used for model training without explicit consent

---

## AI Usage Tracking (ApiUsage Table)

Every AI interaction is logged in the `ApiUsage` table for monitoring and cost control:

```
ApiUsage {
  id           : UUID
  date         : String (YYYY-MM-DD)
  requestCount : Int    (number of API calls that day)
  totalTokens  : Int    (total tokens consumed)
}
```

### Monitoring Thresholds
- **Daily alert:** requestCount > 500 or totalTokens > 500,000
- **Weekly review:** Cost report generated every Monday
- **Anomaly detection:** Spike in requests > 3× daily average triggers investigation

### Cost Optimization Strategies
- Cache frequent policy queries (TTL: 1 hour)
- Short-circuit simple factual queries before hitting the LLM
- Use smaller models for classification tasks (intent detection)
- Rate-limit unauthenticated users to 10 queries/session

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2024-01 | Initial launch — product search + FAQ |
| 1.1 | 2024-03 | Order status lookup added |
| 1.2 | 2024-06 | Personalization by user profile |
| 2.0 | 2024-11 | Full RAG pipeline, review sentiment integration |
| 2.1 | 2025-01 | Multilingual support (French, Spanish beta) |
| 2.2 | 2025-06 | Escalation logic v2, ApiUsage monitoring |
