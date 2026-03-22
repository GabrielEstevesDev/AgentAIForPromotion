"use client";

import { useEffect, useState } from "react";
import { FileText, Loader2 } from "lucide-react";

type DocInfo = {
  filename: string;
  title: string;
  size: number;
};

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL
  ? `${process.env.NEXT_PUBLIC_BACKEND_URL}/api`
  : "/api";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocInfo[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [loadingDocs, setLoadingDocs] = useState(true);

  useEffect(() => {
    async function fetchDocs() {
      setLoadingDocs(true);
      try {
        const res = await fetch(`${API_BASE}/documents`);
        const data: DocInfo[] = await res.json();
        setDocuments(data);
        if (data.length > 0) {
          setSelectedDoc(data[0].filename);
        }
      } catch {
        setDocuments([]);
      } finally {
        setLoadingDocs(false);
      }
    }
    void fetchDocs();
  }, []);

  const selectedInfo = documents.find((d) => d.filename === selectedDoc);
  const pdfUrl = selectedDoc
    ? `${API_BASE}/documents/${selectedDoc}/pdf`
    : null;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <header className="flex shrink-0 items-center justify-between border-b border-[var(--border)] px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-[color:color-mix(in_srgb,var(--accent)_15%,transparent)] text-[var(--accent)]">
            <FileText size={20} />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-[var(--foreground)]">
              Knowledge Base
            </h1>
            <p className="text-xs text-[var(--muted)]">
              Documents the agent uses for RAG search
            </p>
          </div>
        </div>
        {selectedInfo && (
          <span className="text-xs text-[var(--muted)]">
            {selectedInfo.title} &middot; {formatFileSize(selectedInfo.size)}
          </span>
        )}
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Document list panel */}
        <div className="flex w-56 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--card)] md:w-72">
          <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
            <FileText size={14} className="text-[var(--accent)]" />
            <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
              Documents
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {loadingDocs
              ? Array.from({ length: 5 }, (_, i) => (
                  <div
                    key={i}
                    className="mb-1.5 h-14 animate-pulse rounded-xl bg-[color:color-mix(in_srgb,var(--foreground)_6%,transparent)]"
                  />
                ))
              : documents.map((doc) => {
                  const isActive = selectedDoc === doc.filename;
                  return (
                    <button
                      key={doc.filename}
                      type="button"
                      onClick={() => setSelectedDoc(doc.filename)}
                      className={`mb-1 flex w-full flex-col rounded-xl px-3 py-2.5 text-left transition ${
                        isActive
                          ? "bg-[color:color-mix(in_srgb,var(--accent)_15%,transparent)]"
                          : "hover:bg-[color:color-mix(in_srgb,var(--foreground)_5%,transparent)]"
                      }`}
                    >
                      <span
                        className={`truncate text-sm ${
                          isActive
                            ? "font-medium text-[var(--accent)]"
                            : "text-[var(--foreground)]"
                        }`}
                      >
                        {doc.title || doc.filename}
                      </span>
                      <span className="mt-0.5 text-[10px] text-[var(--muted)]">
                        {formatFileSize(doc.size)}
                      </span>
                    </button>
                  );
                })}
          </div>
        </div>

        {/* PDF viewer */}
        <div className="flex flex-1 flex-col overflow-hidden bg-[var(--background)]">
          {loadingDocs ? (
            <div className="flex flex-1 items-center justify-center">
              <Loader2 size={24} className="animate-spin text-[var(--accent)]" />
            </div>
          ) : pdfUrl ? (
            <iframe
              key={pdfUrl}
              src={pdfUrl}
              className="h-full w-full flex-1 border-0"
              title={selectedInfo?.title ?? "Document"}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center text-sm text-[var(--muted)]">
              Select a document to view it.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
