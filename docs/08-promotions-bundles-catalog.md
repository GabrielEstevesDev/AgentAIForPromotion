# Promotions & Bundles Catalog

## Overview

This document describes the platform's discount logic, bundle strategies, seasonal promotions, and pricing rules. The AI assistant uses this to answer questions about deals, coupon codes, and best-value purchases.

---

## Discount Structure

### Threshold Discounts

Automatic discounts applied at checkout based on cart value:

| Cart Total | Discount |
|---|---|
| $0 – $49.99 | No discount |
| $50 – $99.99 | Free standard shipping |
| $100 – $149.99 | Free shipping + 5% off |
| $150 – $249.99 | Free shipping + 10% off |
| $250+ | Free shipping + 15% off |

### Quantity Discounts

Applied when buying multiple units of the same product:

| Quantity | Discount |
|---|---|
| 2 units | 5% off per unit |
| 3–4 units | 10% off per unit |
| 5+ units | 15% off per unit |

Quantity discounts apply to most categories. Exceptions: Books, limited-edition Electronics, and Premium Beauty items.

---

## Bundle Categories

### What is a Bundle?
A bundle is a curated set of complementary products sold together at a combined price lower than buying each item separately. Bundles offer **10–25% savings** compared to individual prices.

### Bundle Types

**Fixed Bundle** — Pre-defined product set, single SKU
- Example: "Home Office Pro Pack" (5 products, fixed configuration)
- Cannot swap items
- Stock managed as a single inventory unit

**Flexible Bundle (Build Your Own)** — Customer selects from a category list
- Select 3+ items from a designated group
- 12% discount applied automatically at checkout
- Example: "Pick any 3 Fitness accessories"

**Gift Bundle** — Seasonal, themed packaging, gift-ready
- Premium packaging included at no extra charge
- Available October–January for holiday season
- Limited quantities

---

## Current Bundles

### Home & Productivity

**Home Office Pro Pack** — *Save 18%*
Includes: Standing Desk Converter + Monitor Riser + Cable Management Kit + Desk Pad Large + USB-C Hub 7-in-1

**Content Creator Station** — *Save 22%*
Includes: Ring Light 18-inch + Green Screen Backdrop + USB Microphone + 4K Webcam + Stream Deck Mini

---

### Fitness & Wellness

**Home Gym Starter Pack** — *Save 20%*
Includes: Adjustable Dumbbell Set + Resistance Bands + Yoga Mat Premium + Foam Roller + Protein Shaker

**Recovery Essentials** — *Save 15%*
Includes: Massage Gun Pro + Foam Roller + Ankle Weights + Compression Socks + Smart Water Bottle

**Morning Wellness Ritual** — *Save 17%*
Includes: Grass-Fed Whey Protein + Organic Matcha Powder + MCT Oil Powder + Electrolyte Powder + Collagen Peptides

---

### Skincare & Beauty

**Complete Skincare Routine** — *Save 19%*
Includes: Vitamin C Serum + Hyaluronic Acid Moisturizer + Retinol Night Cream + SPF 50 Sunscreen + Micellar Water

**Clean Beauty Starter** — *Save 14%*
Includes: Charcoal Face Mask + Rosehip Oil Organic + Jade Roller & Gua Sha + Bamboo Toothbrush + Natural Deodorant

---

### Outdoor & Adventure

**Adventure Ready Kit** — *Save 21%*
Includes: Camping Hammock Double + Portable Water Filter + Tactical Flashlight + Collapsible Hiking Poles + Waterproof Rain Jacket

**Garden Pro Pack** — *Save 16%*
Includes: Raised Garden Bed 4x4 + Seed Starting Kit + Compost Bin + Gardening Gloves + Garden Kneeler

---

### Pet Care

**New Pet Owner Kit** — *Save 18%*
Includes: Automatic Pet Feeder + Slow Feeder Bowl + Orthopedic Dog Bed + Grooming Brush + Calming Collar

---

### Kitchen Essentials

**Zero-Waste Kitchen Kit** — *Save 15%*
Includes: Beeswax Wraps + Compost Bin + Bamboo Cutting Board Set + Digital Kitchen Scale + Silicone Spatula Set

---

## Promo Codes

### How Promo Codes Work
- Applied at checkout in the **Promo Code** field
- One promo code per order (cannot stack with other codes)
- Stacks with threshold discounts and quantity discounts
- Codes are case-insensitive

### Code Types

| Code Type | Example | Discount |
|---|---|---|
| Welcome code | WELCOME10 | 10% off first order |
| Newsletter signup | NEWSLETTER15 | 15% off next order |
| Seasonal | SUMMER25 | 25% off selected categories |
| Flash sale | FLASH48 | 20% off (48-hour window) |
| Referral | FRIEND20 | 20% off (referred friend's first order) |
| Loyalty | LOYAL5 | 5% off every order (loyalty tier) |

### Promo Code Rules
- Cannot be applied to already-discounted bundle prices
- Cannot be used to purchase gift cards
- Minimum cart value of $25 applies to most codes
- Expired codes return a clear error message at checkout

---

## Seasonal Promotions Calendar

### January — New Year New You
**Focus:** Fitness, Self-care, Office productivity
- Up to 30% off Fitness category
- Home Gym Starter Pack at maximum discount
- Free shaker bottle with any protein purchase

### February — Valentine's Day
**Focus:** Beauty, Books, Toys & Games
- Gift bundles with premium packaging
- Free gift wrapping on orders over $40
- "Date Night" bundle (Board games + snacks)

### March–April — Spring Refresh
**Focus:** Garden & Outdoor, Home & Kitchen
- Garden Pro Pack featured
- Free seeds with any garden bed purchase
- Kitchen bundle promotions

### May — Mother's Day
**Focus:** Beauty, Home & Kitchen, Books
- 20% off Beauty bundles
- Personalized recommendation quiz ("Find the perfect gift")

### July — Summer Sale
**Focus:** Outdoor, Fitness, Electronics
- Sitewide 15–25% off
- Flash deals every 24 hours for 7 days
- Bundle discounts increased by 5%

### September — Back to School / Work
**Focus:** Electronics, Office Supplies, Books
- Student discount: 10% with .edu email verification
- Bundle-and-save on home office setups

### November — Black Friday & Cyber Monday
**Focus:** All categories
- Largest sale of the year: 20–50% off
- Flash deals every 2 hours
- Free overnight shipping on orders $100+
- Bundle discounts stacked with sitewide sale

### December — Holiday Gift Season
**Focus:** Toys, Electronics, Beauty, Gift Bundles
- Gift bundles with complimentary premium packaging
- Last-order date guidance for Christmas delivery
- New Year preview deals from Dec 26

---

## Loyalty Program

### Tiers

| Tier | Spend Threshold | Benefits |
|---|---|---|
| Bronze | $0–$199/year | Birthday discount (5%), early sale access |
| Silver | $200–$499/year | 5% cashback, free returns, priority support |
| Gold | $500–$999/year | 8% cashback, free express shipping |
| Platinum | $1,000+/year | 12% cashback, free overnight shipping, personal shopper |

### Points System
- Earn **1 point per $1 spent**
- **100 points = $1 store credit**
- Bonus points for writing verified reviews (+50 pts), referring friends (+200 pts)
- Points expire after **12 months** of account inactivity
