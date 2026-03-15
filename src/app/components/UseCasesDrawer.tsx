"use client";

import { useState } from "react";
import { X, Shield, Database, BookOpen, Globe, BarChart3, ShieldCheck } from "lucide-react";
import type { UseCaseCardsPayload, UseCaseCard } from "@/lib/types";

// ---------------------------------------------------------------------------
// Default fallback data
// ---------------------------------------------------------------------------

const DEFAULT_DATA: UseCaseCardsPayload = {
  front_actions: [
    {
      id: "front-sql",
      category: "SQL",
      title: "Top Products by Revenue",
      description: "See which products generate the most revenue",
      tool_badges: ["SQL"],
      prompt: "Show me the top 10 products by revenue.",
      requires_hitl: false,
    },
    {
      id: "front-rag",
      category: "RAG",
      title: "Return Policy",
      description: "Look up return and refund policies",
      tool_badges: ["RAG"],
      prompt: "What is the return policy?",
      requires_hitl: false,
    },
    {
      id: "front-web",
      category: "WEB",
      title: "E-commerce Trends",
      description: "Latest industry trends and insights",
      tool_badges: ["WEB"],
      prompt: "What are the latest e-commerce trends for 2025?",
      requires_hitl: false,
    },
    {
      id: "front-chart",
      category: "PYTHON_CHART",
      title: "Revenue by Month Chart",
      description: "Visualize monthly revenue trends",
      tool_badges: ["SQL", "PYTHON_CHART"],
      prompt: "Create a bar chart of revenue by month.",
      requires_hitl: false,
    },
    {
      id: "front-hitl",
      category: "HITL",
      title: "Draft Refund Email",
      description: "Generate a customer refund email for review",
      tool_badges: ["RAG", "SQL", "HITL"],
      prompt: "Draft a refund email for the most recent cancelled order.",
      requires_hitl: true,
    },
  ],
  categories: [
    {
      id: "SQL",
      label: "SQL Queries",
      cards: [
        { id: "sql-1", title: "Customer Count", description: "Total customers in the database", tool_badges: ["SQL"], prompt: "How many customers are in the database?", requires_hitl: false },
        { id: "sql-2", title: "Pending Orders", description: "All orders awaiting processing", tool_badges: ["SQL"], prompt: "List all pending orders with customer names.", requires_hitl: false },
        { id: "sql-3", title: "Revenue by Category", description: "Revenue breakdown per product category", tool_badges: ["SQL"], prompt: "Show revenue by product category.", requires_hitl: false },
        { id: "sql-4", title: "Low Stock Products", description: "Products with critically low inventory", tool_badges: ["SQL"], prompt: "Which products have the lowest stock levels?", requires_hitl: false },
        { id: "sql-5", title: "Top Customers", description: "Highest-spending customers", tool_badges: ["SQL"], prompt: "Who are the top 10 customers by total spend?", requires_hitl: false },
        { id: "sql-6", title: "AI Workflow Discovery", description: "Identify which workflows an AI copilot could automate", tool_badges: ["SQL"], prompt: "Analyze this business and identify which workflows an AI copilot could automate. Show data to support each recommendation.", requires_hitl: false },
      ],
    },
    {
      id: "RAG",
      label: "Knowledge Base",
      cards: [
        { id: "rag-1", title: "Shipping Policy", description: "Delivery times and shipping options", tool_badges: ["RAG"], prompt: "What are the shipping options and delivery times?", requires_hitl: false },
        { id: "rag-2", title: "Warranty Info", description: "Product warranty details", tool_badges: ["RAG"], prompt: "What is the warranty policy for electronics?", requires_hitl: false },
        { id: "rag-3", title: "FAQ", description: "Common customer questions", tool_badges: ["RAG"], prompt: "What are the most common customer FAQs?", requires_hitl: false },
        { id: "rag-4", title: "Product Guide", description: "Product categories and comparisons", tool_badges: ["RAG"], prompt: "Give me an overview of product categories.", requires_hitl: false },
        { id: "rag-5", title: "Policy Lookup Demo", description: "Show how instant policy lookup helps customer service", tool_badges: ["RAG"], prompt: "Show how instant policy lookup could help a customer service team. Demo it with our return and shipping policies.", requires_hitl: false },
      ],
    },
    {
      id: "WEB",
      label: "Web Search",
      cards: [
        { id: "web-1", title: "Market Trends", description: "Current e-commerce market trends", tool_badges: ["WEB"], prompt: "What are the current e-commerce market trends?", requires_hitl: false },
        { id: "web-2", title: "Competitor Analysis", description: "How competitors are pricing similar products", tool_badges: ["WEB"], prompt: "What are competitors charging for electronics?", requires_hitl: false },
        { id: "web-3", title: "AI in Retail", description: "How AI is transforming retail", tool_badges: ["WEB"], prompt: "How is AI being used in retail and e-commerce?", requires_hitl: false },
        { id: "web-4", title: "Holiday Season Tips", description: "Best practices for seasonal sales", tool_badges: ["WEB"], prompt: "What are the best practices for holiday season e-commerce sales?", requires_hitl: false },
        { id: "web-5", title: "AI Copilot Adoption", description: "How AI copilots are being adopted in e-commerce", tool_badges: ["WEB"], prompt: "Research how AI copilots are being adopted in e-commerce and compare to our capabilities.", requires_hitl: false },
      ],
    },
    {
      id: "PYTHON_CHART",
      label: "Charts & Analytics",
      cards: [
        { id: "chart-1", title: "Sales Over Time", description: "Line chart of monthly sales", tool_badges: ["SQL", "PYTHON_CHART"], prompt: "Create a line chart showing sales trends over time.", requires_hitl: false },
        { id: "chart-2", title: "Category Pie Chart", description: "Revenue share by category", tool_badges: ["SQL", "PYTHON_CHART"], prompt: "Create a pie chart of revenue distribution by product category.", requires_hitl: false },
        { id: "chart-3", title: "Rating Distribution", description: "Histogram of product ratings", tool_badges: ["SQL", "PYTHON_CHART"], prompt: "Create a bar chart of the rating distribution across all products.", requires_hitl: false },
        { id: "chart-4", title: "Inventory Levels", description: "Bar chart of stock levels by product", tool_badges: ["SQL", "PYTHON_CHART"], prompt: "Create a bar chart of inventory levels for the top 15 products.", requires_hitl: false },
        { id: "chart-5", title: "Executive Dashboard", description: "AI-powered reporting dashboard demo", tool_badges: ["SQL", "PYTHON_CHART"], prompt: "Create an executive dashboard that demonstrates AI-powered reporting. Include revenue trends and key metrics.", requires_hitl: false },
      ],
    },
    {
      id: "HITL",
      label: "Approval Workflows",
      cards: [
        { id: "hitl-1", title: "Refund Email Draft", description: "Draft a customer refund/dispute email for approval", tool_badges: ["RAG", "SQL", "HITL"], prompt: "Draft a refund email for the most recent cancelled order.", requires_hitl: true },
        { id: "hitl-2", title: "30-Day Promo Strategy", description: "Build a promotion strategy requiring budget approval", tool_badges: ["SQL", "PYTHON_CHART", "HITL"], prompt: "Create a 30-day promotion strategy to boost revenue.", requires_hitl: true },
        { id: "hitl-3", title: "Replenishment Order", description: "Generate a purchase order draft for low-stock items and update inventory", tool_badges: ["SQL", "PYTHON_CHART", "HITL"], prompt: "Analyze sales velocity and create a replenishment purchase order for items running low on stock.", requires_hitl: true },
        { id: "hitl-4", title: "VIP Compensation", description: "Draft a compensation offer for a VIP customer complaint", tool_badges: ["RAG", "SQL", "HITL"], prompt: "Draft a VIP compensation email for a customer who received a damaged product.", requires_hitl: true },
        { id: "hitl-5", title: "Error Prevention Demo", description: "Show how AI-assisted approval prevents costly operational errors", tool_badges: ["SQL", "HITL"], prompt: "Walk through how AI-assisted approval prevents costly errors in operations. Demo with a replenishment scenario.", requires_hitl: true },
      ],
    },
  ],
};

// ---------------------------------------------------------------------------
// Tab config
// ---------------------------------------------------------------------------

const TABS = [
  { id: "SQL", label: "SQL", icon: Database },
  { id: "RAG", label: "RAG", icon: BookOpen },
  { id: "WEB", label: "WEB", icon: Globe },
  { id: "PYTHON_CHART", label: "Charts", icon: BarChart3 },
  { id: "HITL", label: "Approval", icon: ShieldCheck },
] as const;

const BADGE_COLORS: Record<string, string> = {
  SQL: "bg-blue-500/15 text-blue-400 border-blue-500/25",
  RAG: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  WEB: "bg-orange-500/15 text-orange-400 border-orange-500/25",
  PYTHON_CHART: "bg-purple-500/15 text-purple-400 border-purple-500/25",
  HITL: "bg-amber-500/15 text-amber-400 border-amber-500/25",
};

const BADGE_LABELS: Record<string, string> = {
  HITL: "Approval",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type UseCasesDrawerProps = {
  isOpen: boolean;
  onClose: () => void;
  onSelectPrompt: (prompt: string) => void;
  data: UseCaseCardsPayload | null;
};

export function UseCasesDrawer({ isOpen, onClose, onSelectPrompt, data }: UseCasesDrawerProps) {
  const [activeTab, setActiveTab] = useState("SQL");
  const cardsData = data ?? DEFAULT_DATA;

  const activeCategory = cardsData.categories.find((c) => c.id === activeTab);

  function handleCardClick(card: UseCaseCard) {
    onSelectPrompt(card.prompt);
    onClose();
  }

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col border-l border-[var(--border)] bg-[var(--background)] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
          <h2 className="text-lg font-semibold text-[var(--foreground)]">Use Cases</h2>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--muted)] transition hover:bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)] hover:text-[var(--foreground)]"
          >
            <X size={18} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-[var(--border)] px-4 pt-2">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 rounded-t-lg px-3 py-2 text-xs font-semibold transition ${
                  activeTab === tab.id
                    ? "border-b-2 border-[var(--accent)] text-[var(--accent)]"
                    : "text-[var(--muted)] hover:text-[var(--foreground)]"
                }`}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Card grid */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {activeCategory?.cards.map((card) => (
              <button
                key={card.id}
                type="button"
                onClick={() => handleCardClick(card)}
                className="group/card flex flex-col gap-2 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4 text-left transition hover:-translate-y-0.5 hover:border-[var(--accent)]/35 hover:shadow-md"
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-[var(--foreground)]">
                    {card.title}
                  </span>
                  {card.requires_hitl && (
                    <Shield size={13} className="text-amber-400" />
                  )}
                </div>
                <p className="text-xs leading-5 text-[var(--muted)]">{card.description}</p>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {card.tool_badges.map((badge) => (
                    <span
                      key={badge}
                      className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${BADGE_COLORS[badge] ?? "bg-gray-500/15 text-gray-400 border-gray-500/25"}`}
                    >
                      {BADGE_LABELS[badge] ?? badge}
                    </span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
