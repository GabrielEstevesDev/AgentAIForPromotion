import "dotenv/config";
import path from "path";
import { PrismaClient } from "@prisma/client";
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";
import { faker } from "@faker-js/faker";

faker.seed(42); // reproductible

const dbPath = path.resolve(process.cwd(), "dev.db");
const adapter = new PrismaBetterSqlite3({ url: `file:${dbPath}` });
const prisma = new PrismaClient({ adapter } as any);

// ─── Constants ────────────────────────────────────────────────────────────────

const ORDER_STATUSES = ["Pending", "Shipped", "Delivered", "Cancelled"] as const;

const CATEGORIES: Record<string, { names: string[]; priceRange: [number, number] }> = {
  Electronics: {
    names: [
      "Wireless Noise-Cancelling Headphones", "Bluetooth Speaker", "Mechanical Keyboard",
      "4K Webcam", "USB-C Hub 7-in-1", "Portable SSD 1TB", "Wireless Charging Pad",
      "Smart LED Desk Lamp", "Ergonomic Mouse", "Dual Monitor Stand", "USB Microphone",
      "Laptop Cooling Pad", "Cable Management Kit", "HDMI 2.1 Cable 6ft",
      "Thunderbolt 4 Dock", "NVMe External Drive 2TB", "Stream Deck Mini",
      "Green Screen Backdrop", "Ring Light 18-inch", "Smart Plug 4-Pack",
    ],
    priceRange: [12.99, 399.99],
  },
  "Home & Kitchen": {
    names: [
      "Stainless Steel French Press", "Cast Iron Skillet 12-inch", "Bamboo Cutting Board Set",
      "Digital Kitchen Scale", "Silicone Spatula Set", "Ceramic Knife Set 5-piece",
      "Instant Pot 6-Quart", "Air Fryer 5.8L", "Cold Brew Coffee Maker",
      "Reusable Beeswax Wraps", "Compost Bin 1.3 Gallon", "Glass Meal Prep Containers",
      "Mandoline Slicer", "Herb Keeper", "Avocado Slicer", "Salad Spinner",
      "Non-stick Wok 14-inch", "Spice Rack Organizer", "Magnetic Knife Strip",
      "Over-Sink Dish Rack",
    ],
    priceRange: [8.99, 149.99],
  },
  Fitness: {
    names: [
      "Adjustable Dumbbell Set 5-52lbs", "Resistance Bands Set", "Yoga Mat Premium 6mm",
      "Pull-Up Bar Doorway", "Foam Roller High-Density", "Jump Rope Speed",
      "Ab Roller Wheel", "Kettlebell 35lb", "Workout Gloves", "Gym Bag 40L",
      "Protein Shaker Bottle", "Massage Gun Pro", "Balance Board",
      "Ankle Weights 5lb Pair", "Battle Rope 1.5-inch", "Push-Up Handles",
      "Medicine Ball 15lb", "Suspension Training System", "Rowing Machine Compact",
      "Smart Water Bottle 32oz",
    ],
    priceRange: [9.99, 299.99],
  },
  Books: {
    names: [
      "Atomic Habits — James Clear", "Deep Work — Cal Newport", "The Pragmatic Programmer",
      "Clean Code — Robert C. Martin", "Designing Data-Intensive Applications",
      "System Design Interview Vol.1", "The Lean Startup — Eric Ries",
      "Zero to One — Peter Thiel", "Thinking, Fast and Slow", "The Psychology of Money",
      "A Philosophy of Software Design", "Refactoring — Martin Fowler",
      "The Art of War — Sun Tzu", "Sapiens — Yuval Noah Harari", "12 Rules for Life",
      "Can't Hurt Me — David Goggins", "The 4-Hour Workweek", "Never Finished — Goggins",
      "Elon Musk — Walter Isaacson", "Steve Jobs — Walter Isaacson",
    ],
    priceRange: [9.99, 39.99],
  },
  "Beauty & Personal Care": {
    names: [
      "Vitamin C Serum 20%", "Hyaluronic Acid Moisturizer", "Retinol Night Cream",
      "Niacinamide 10% Toner", "SPF 50 Sunscreen Daily", "Micellar Water 400ml",
      "Charcoal Face Mask", "Rosehip Oil Organic", "Eye Cream with Caffeine",
      "Lip Balm SPF 30 Set", "Beard Grooming Kit", "Electric Toothbrush Pro",
      "Jade Roller & Gua Sha", "Exfoliating Body Scrub", "Tea Tree Body Wash",
      "Argan Oil Hair Serum", "Bamboo Toothbrush 4-Pack", "Natural Deodorant",
      "Collagen Peptides Supplement", "Biotin Gummies 10000mcg",
    ],
    priceRange: [6.99, 89.99],
  },
  "Office Supplies": {
    names: [
      "Standing Desk Converter", "Ergonomic Chair Lumbar Cushion", "Monitor Riser",
      "Wireless Keyboard & Mouse Combo", "Desk Organizer Bamboo", "Pen Holder Set",
      "Sticky Notes Bulk Pack", "Label Maker", "Paper Shredder 8-Sheet",
      "Whiteboard 36x24", "Dry Erase Markers 12-Pack", "File Organizer Mesh",
      "Cable Clips 30-Pack", "Desk Pad Large 35x17", "Notebook A5 Hardcover",
      "Fountain Pen Set", "Highlighters Pastel 6-Pack", "Stapler Heavy-Duty",
      "Tape Dispenser + Rolls", "Business Card Holder",
    ],
    priceRange: [5.99, 199.99],
  },
  "Outdoor & Garden": {
    names: [
      "Camping Hammock Double", "Portable Water Filter", "Tactical Flashlight 1000lm",
      "Solar Garden Lights 12-Pack", "Collapsible Hiking Poles", "Waterproof Rain Jacket",
      "Gardening Gloves Nitrile", "Raised Garden Bed 4x4", "Seed Starting Kit",
      "Compost Tumbler 37-Gallon", "Garden Kneeler Seat", "Weed Fabric Roll",
      "Bird Feeder Squirrel-Proof", "Pressure Washer 2000PSI", "Leaf Blower Cordless",
      "Hedge Trimmer 20V", "Lawn Aerator Sandals", "Fire Pit 36-inch",
      "Patio String Lights 48ft", "Outdoor Thermometer",
    ],
    priceRange: [11.99, 249.99],
  },
  "Toys & Games": {
    names: [
      "LEGO Architecture Set", "Rubik's Cube 3x3 Speed", "Chess Set Wooden Deluxe",
      "Card Game — Exploding Kittens", "Ticket to Ride Board Game", "Catan Board Game",
      "Jenga Giant", "Puzzle 1000 pieces Nature", "Magnetic Drawing Board",
      "Kinetic Sand 2lb", "Slime Making Kit", "Remote Control Car Offroad",
      "Drone Mini for Kids", "Building Blocks 500pcs", "Science Kit 30 Experiments",
      "Telescope for Beginners", "Microscope Kids 100x-400x", "Coding Robot Bee-Bot",
      "Sensory Fidget Toy Set", "Origami Paper 200 Sheets",
    ],
    priceRange: [8.99, 129.99],
  },
  "Pet Supplies": {
    names: [
      "Automatic Pet Feeder", "Self-Cleaning Litter Box", "Dog Harness No-Pull",
      "Cat Scratching Post Tower", "Interactive Laser Toy", "Slow Feeder Bowl",
      "Pet GPS Tracker", "Orthopedic Dog Bed", "Retractable Leash 16ft",
      "Dog Training Clicker Set", "Cat Tunnel Toy", "Fish Tank 10 Gallon Starter",
      "Bird Cage Large", "Small Animal Cage", "Reptile Heat Mat",
      "Pet Carrier Airline-Approved", "Grooming Brush Self-Cleaning", "Pet Stroller 3-Wheel",
      "Calming Collar Dog", "Probiotics for Dogs 120ct",
    ],
    priceRange: [7.99, 179.99],
  },
  "Clothing & Accessories": {
    names: [
      "Merino Wool Base Layer", "Compression Socks 3-Pack", "Running Belt Waist Pack",
      "Wool Beanie Unisex", "Leather Bifold Wallet", "Minimalist Watch Men",
      "Silk Scrunchies 6-Pack", "Polarized Sunglasses", "Canvas Tote Bag",
      "Laptop Backpack 30L", "Fanny Pack Waterproof", "Wool Scarf Cashmere",
      "Bamboo Socks 5-Pack", "Reflective Running Vest", "Gloves Touch Screen Winter",
      "Balaclava Ski Mask", "Sun Hat Wide Brim", "Packable Down Jacket",
      "Slip-On Shoes Unisex", "Compression Knee Sleeves",
    ],
    priceRange: [12.99, 149.99],
  },
  "Food & Grocery": {
    names: [
      "Organic Matcha Powder 100g", "Raw Honey Manuka 250g", "Himalayan Pink Salt Grinder",
      "Organic Coconut Oil 16oz", "Dark Chocolate 85% 10-Pack", "Grass-Fed Whey Protein",
      "MCT Oil Powder", "Organic Chia Seeds 2lb", "Kombucha Starter Kit",
      "Cold Brew Coffee Concentrate", "Organic Oat Flour 5lb", "Nutritional Yeast 500g",
      "Almond Butter No-Stir", "Organic Maple Syrup Grade A", "Freeze-Dried Berries Mix",
      "Cacao Powder Raw 1lb", "Collagen Coffee Creamer", "Electrolyte Powder 60-Pack",
      "Bone Broth Concentrate", "Organic Turmeric Capsules",
    ],
    priceRange: [6.99, 59.99],
  },
  "Automotive": {
    names: [
      "Dash Cam 4K Front & Rear", "Car Vacuum Cordless", "Phone Mount Dashboard",
      "Jump Starter 2000A", "Tire Inflator Portable", "Seat Gap Organizer",
      "Car Air Purifier HEPA", "Trunk Organizer Collapsible", "Car Wax Polish Kit",
      "Microfiber Towels Auto 20-Pack", "OBD2 Scanner Bluetooth", "Blind Spot Mirrors",
      "Steering Wheel Cover", "Car Seat Cover Set", "Emergency Roadside Kit",
      "Ice Scraper Heavy-Duty", "Parking Sensor Kit", "Car Code Reader",
      "LED Interior Lights Kit", "Rain Repellent Spray",
    ],
    priceRange: [9.99, 199.99],
  },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function randomInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function randomFloat(min: number, max: number, decimals = 2): number {
  return parseFloat((Math.random() * (max - min) + min).toFixed(decimals));
}

function randomPastDate(daysBack = 730): Date {
  return faker.date.past({ years: 2 });
}

function skuFor(category: string, index: number): string {
  const prefix = category.replace(/[^A-Z]/gi, "").slice(0, 3).toUpperCase();
  return `${prefix}-${String(index).padStart(5, "0")}`;
}

function reviewText(rating: number, productName: string): string {
  const positive = [
    `Absolutely love this ${productName}. Exceeded my expectations!`,
    `Best purchase I've made this year. The ${productName} is top notch.`,
    `Outstanding quality. Highly recommend the ${productName} to everyone.`,
    `The ${productName} arrived quickly and works perfectly. Very happy!`,
    `Five stars all the way. The ${productName} is a game changer.`,
    `I was skeptical at first, but the ${productName} blew me away.`,
    `Incredible value for money. The ${productName} is built to last.`,
  ];
  const neutral = [
    `The ${productName} is decent but nothing extraordinary.`,
    `Good product overall. The ${productName} does what it promises.`,
    `The ${productName} is okay. Took a while to ship but worth it.`,
    `Solid buy. The ${productName} meets expectations, nothing more.`,
    `Not bad. The ${productName} has some minor flaws but works fine.`,
  ];
  const negative = [
    `Disappointed with the ${productName}. Quality feels cheap.`,
    `The ${productName} stopped working after two weeks. Not impressed.`,
    `Wouldn't recommend the ${productName}. Doesn't match the description.`,
    `Poor packaging, the ${productName} arrived damaged.`,
    `Expected much more from the ${productName}. Customer service was unhelpful.`,
  ];
  if (rating >= 4) return pick(positive);
  if (rating === 3) return pick(neutral);
  return pick(negative);
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  console.log("🌱 Seeding database...\n");

  // ── 1. Customers (60) ──────────────────────────────────────────────────────
  console.log("👤 Creating customers...");
  const customerData = Array.from({ length: 60 }, (_, i) => {
    const firstName = faker.person.firstName();
    const lastName = faker.person.lastName();
    return {
      firstName,
      lastName,
      email: `${firstName.toLowerCase()}.${lastName.toLowerCase()}${i}@${faker.internet.domainName()}`,
      phone: faker.phone.number({ style: "national" }),
      createdAt: randomPastDate(),
    };
  });

  await prisma.customer.createMany({ data: customerData });
  const customers = await prisma.customer.findMany();
  console.log(`  ✓ ${customers.length} customers created`);

  // ── 2. Products (240 = 12 categories × 20) ────────────────────────────────
  console.log("📦 Creating products...");
  const productData: {
    name: string; description: string; price: number;
    category: string; sku: string;
  }[] = [];

  let skuIndex = 1;
  for (const [category, config] of Object.entries(CATEGORIES)) {
    for (const name of config.names) {
      productData.push({
        name,
        description: faker.commerce.productDescription() +
          ` This ${name.toLowerCase()} is crafted for durability and performance. ` +
          faker.lorem.sentences(2),
        price: randomFloat(...config.priceRange),
        category,
        sku: skuFor(category, skuIndex++),
      });
    }
  }

  await prisma.product.createMany({ data: productData });
  const products = await prisma.product.findMany();
  console.log(`  ✓ ${products.length} products created`);

  // ── 3. Inventory (1 per product) ──────────────────────────────────────────
  console.log("🏭 Creating inventory...");
  await prisma.inventory.createMany({
    data: products.map((p) => ({
      productId: p.id,
      stockLevel: randomInt(0, 500),
      lastRestock: randomPastDate(365),
    })),
  });
  console.log(`  ✓ ${products.length} inventory records created`);

  // ── 4. Orders (80) with OrderItems ────────────────────────────────────────
  console.log("🛒 Creating orders and order items...");
  let totalItems = 0;

  for (let i = 0; i < 80; i++) {
    const customer = pick(customers);
    const status = pick([
      "Pending", "Pending",
      "Shipped", "Shipped", "Shipped",
      "Delivered", "Delivered", "Delivered", "Delivered",
      "Cancelled",
    ]);
    const orderDate = randomPastDate(540);

    // 1 to 5 distinct products per order
    const itemCount = randomInt(1, 5);
    const shuffled = [...products].sort(() => 0.5 - Math.random());
    const selected = shuffled.slice(0, itemCount);

    const items = selected.map((p) => ({
      productId: p.id,
      quantity: randomInt(1, 4),
      unitPrice: p.price, // snapshot
    }));

    const totalAmount = parseFloat(
      items.reduce((sum, it) => sum + it.unitPrice * it.quantity, 0).toFixed(2)
    );

    const order = await prisma.order.create({
      data: {
        customerId: customer.id,
        orderDate,
        status,
        totalAmount,
        orderItems: {
          create: items,
        },
      },
    });

    totalItems += items.length;
  }

  const orderCount = await prisma.order.count();
  console.log(`  ✓ ${orderCount} orders created (${totalItems} line items)`);

  // Status breakdown
  const statusGroups = await prisma.order.groupBy({
    by: ["status"],
    _count: { status: true },
  });
  for (const g of statusGroups) {
    console.log(`     └─ ${g.status}: ${g._count.status}`);
  }

  // ── 5. Reviews (3-6 reviews per product, subset of products = 180 products) ─
  console.log("⭐ Creating reviews...");
  const reviewData: {
    productId: string; customerId: string;
    rating: number; comment: string; createdAt: Date;
  }[] = [];

  // Review ~75% of products
  const reviewedProducts = products.filter(() => Math.random() < 0.75);

  for (const product of reviewedProducts) {
    const reviewCount = randomInt(3, 6);
    const usedCustomerIds = new Set<string>();

    for (let r = 0; r < reviewCount; r++) {
      // Avoid same customer reviewing same product twice
      let customer = pick(customers);
      let attempts = 0;
      while (usedCustomerIds.has(customer.id) && attempts < 20) {
        customer = pick(customers);
        attempts++;
      }
      if (usedCustomerIds.has(customer.id)) continue;
      usedCustomerIds.add(customer.id);

      const rating = pick([1, 2, 3, 3, 4, 4, 4, 5, 5, 5]);
      reviewData.push({
        productId: product.id,
        customerId: customer.id,
        rating,
        comment: reviewText(rating, product.name),
        createdAt: randomPastDate(500),
      });
    }
  }

  await prisma.review.createMany({ data: reviewData });
  console.log(`  ✓ ${reviewData.length} reviews created`);

  // ── 6. Suppliers (5) ─────────────────────────────────────────────────────
  console.log("🏢 Creating suppliers...");
  const supplierData = [
    { name: "EcoSource Trading", email: "procurement@ecosource.io", phone: "+1-555-0404" },
  ];

  await prisma.supplier.createMany({ data: supplierData });
  const suppliers = await prisma.supplier.findMany();
  console.log(`  ✓ ${suppliers.length} suppliers created`);

  // ── 7. ApiUsage (last 30 days) ────────────────────────────────────────────
  console.log("📊 Creating API usage records...");
  const apiUsageData = Array.from({ length: 30 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (29 - i));
    return {
      date: d.toISOString().split("T")[0],
      requestCount: randomInt(10, 250),
      totalTokens: randomInt(5000, 120000),
    };
  });

  await prisma.apiUsage.createMany({ data: apiUsageData });
  console.log(`  ✓ 30 API usage records created`);

  // ── Summary ───────────────────────────────────────────────────────────────
  console.log("\n✅ Seed complete!\n");
  console.log("📋 Summary:");
  console.log(`   Customers   : ${await prisma.customer.count()}`);
  console.log(`   Products    : ${await prisma.product.count()}`);
  console.log(`   Inventory   : ${await prisma.inventory.count()}`);
  console.log(`   Orders      : ${await prisma.order.count()}`);
  console.log(`   Order Items : ${await prisma.orderItem.count()}`);
  console.log(`   Reviews     : ${await prisma.review.count()}`);
  console.log(`   API Usage   : ${await prisma.apiUsage.count()}`);
  console.log(`   Suppliers   : ${await prisma.supplier.count()}`);
}

main()
  .catch((e) => {
    console.error("❌ Seed failed:", e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
