# Reviews & Rating Policy

## Overview

This document describes the platform's review and rating system — how reviews are collected, displayed, moderated, and used by the AI recommendation engine. It also covers customer trust mechanisms and the role of reviews in the product discovery experience.

---

## Rating System

### Star Scale

All products are rated on a **1–5 star scale**:

| Stars | Label | Meaning |
|-------|-------|---------|
| ⭐⭐⭐⭐⭐ | Excellent | Exceeded expectations — highly recommend |
| ⭐⭐⭐⭐ | Good | Solid product with minor drawbacks |
| ⭐⭐⭐ | Average | Meets basic expectations, nothing special |
| ⭐⭐ | Poor | Significant issues, hard to recommend |
| ⭐ | Terrible | Defective, misrepresented, or major failure |

### Aggregate Score Calculation

The displayed product rating is a **weighted average** — not a simple mean. Recent reviews (last 90 days) carry **1.5× the weight** of older reviews to reflect current product quality.

```
Weighted Score = (Σ recent_rating × 1.5 + Σ older_rating × 1.0) / Total Weight
```

Products with fewer than **3 reviews** display a "New — Not Yet Rated" badge instead of a score.

---

## Who Can Leave a Review?

### Eligibility Rules
- Customer must have a **verified purchase** of the exact product (matched by order ID)
- Order status must be **Delivered**
- A customer can only leave **one review per product per purchase**
- Reviews can be submitted from the time of delivery to **6 months** after

### Why Verified Purchase Only?
Limiting reviews to verified buyers ensures:
- Authenticity of feedback
- Prevention of competitor manipulation
- Trust signal visibility ("Verified Purchase" badge)

---

## Review Content Guidelines

### What Makes a Good Review
A helpful review typically includes:
- **Product quality** — build, materials, durability
- **Accuracy** — does it match the description and photos?
- **Use case context** — who uses it, how often, for what purpose
- **Comparison** — vs previous product or competitors (optional)
- **Specific pros and cons** — not just "great product!"

### Permitted Content
- Honest opinions, positive or negative
- Photos or videos of the product
- Mentions of shipping experience (factual)
- Follow-up reviews after extended use

### Prohibited Content
Reviews will be rejected or removed if they contain:
- **Hate speech**, discriminatory language, or personal attacks
- **Spam or promotional content** (links, promo codes)
- **Irrelevant content** (discussing a different product, unrelated topics)
- **False claims** that cannot be substantiated
- **Profanity** or explicit content
- **Competitor bashing** without factual basis
- **Incentivized reviews** not disclosed as such

---

## Review Moderation

### Moderation Process

1. **Automatic filter** — AI scans for prohibited keywords, spam patterns, and policy violations
2. **Human review** — flagged reviews are reviewed by a moderation team within **48 hours**
3. **Published or rejected** — customer is notified by email in both cases

### Moderation Timeline
- Standard reviews: published within **24–48 hours**
- Reviews with photos/videos: up to **72 hours** (additional content check)
- Reviews flagged for policy check: up to **5 business days**

### Appealing a Rejected Review
If your review was rejected and you believe it complies with guidelines:
- Contact support with your order number and review content
- The moderation team will re-evaluate within **3 business days**

---

## Review Display & Sorting

### Default Sort
By default, reviews are sorted by **Helpfulness Score** — a combination of:
- Number of "Helpful" votes from other customers
- Recency of the review
- Verified purchase status

### Available Sort Options
- Most Helpful
- Most Recent
- Highest Rated
- Lowest Rated

### Review Filters
Customers can filter by:
- Star rating (1–5)
- Verified purchase only
- Reviews with photos
- Keyword search within reviews

---

## Review Voting

Any logged-in customer can vote on existing reviews:
- **Helpful** 👍 — increases the review's visibility
- **Not Helpful** 👎 — decreases visibility (doesn't remove the review)

Reviews with high helpful votes are surfaced in **Top Reviews** sections.

---

## Trust & Credibility Signals

### Verified Purchase Badge
Displayed on reviews from customers with a confirmed order. The most important trust signal — weighted higher in the recommendation algorithm.

### Top Reviewer Badge
Awarded to customers with:
- 10+ published reviews
- Average helpfulness score above 80%
- No moderation violations

### Early Reviewer
Applied to reviews submitted within **7 days** of delivery. Indicates timely, fresh feedback.

---

## AI Use of Review Data

Reviews are a primary data source for several AI features:

### Sentiment Analysis
The `comment` field in each review is processed by the AI to:
- Extract positive and negative sentiment per product attribute
- Identify recurring complaints (e.g., "battery life", "sizing too small")
- Generate **AI Summary cards** — 2–3 sentence product summaries derived from all reviews

### Recommendation Engine
Review signals used in recommendations:
- **Rating** — higher-rated products ranked up
- **Review volume** — more reviews = more confidence
- **Keyword match** — review content matches user's search intent
- **Recency** — products with recent positive reviews ranked higher

### Inventory Signals
Products with a sustained pattern of 1–2 star reviews trigger:
- Automatic quality alert to the purchasing team
- Potential temporary deactivation pending supplier investigation

---

## Review Response Policy (Seller / Admin)

Admins can post **one official response** per review:
- Response is publicly visible under the review
- Used for acknowledging issues, providing clarification, or thanking customers
- Responses cannot edit or dispute factual claims — only add context

---

## Frequently Asked Questions — Reviews

**Q: My review says "Under Review" — what does that mean?**
A: Your review is in the moderation queue. It will be published or rejected within 48–72 hours.

**Q: Can I review the same product multiple times?**
A: No. You can edit your existing review up to 14 days after posting.

**Q: The product I received was different from what was described. Can I mention this in my review?**
A: Yes. Factual descriptions of discrepancies between listing and received product are allowed and encouraged.

**Q: Can I write a review if I received the product as a gift?**
A: Only the person who placed and received the order can leave a verified review. Gift recipients cannot post verified reviews.

**Q: Will leaving a negative review affect my account?**
A: Absolutely not. Honest negative reviews are valued. Accounts are never penalized for critical but factual reviews.
