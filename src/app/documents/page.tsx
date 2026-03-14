"use client";

import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Download, FileText, Loader2 } from "lucide-react";

type DocInfo = {
  filename: string;
  title: string;
  size: number;
};

const BACKEND_URL = "http://localhost:8001";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocInfo[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [loadingContent, setLoadingContent] = useState(false);

  useEffect(() => {
    async function fetchDocs() {
      setLoadingDocs(true);
      try {
        const res = await fetch(`${BACKEND_URL}/api/documents`);
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

  const fetchContent = useCallback(async (filename: string) => {
    setLoadingContent(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/documents/${filename}`);
      const data = await res.json();
      setContent(data.content ?? "");
    } catch {
      setContent(null);
    } finally {
      setLoadingContent(false);
    }
  }, []);

  useEffect(() => {
    if (selectedDoc) {
      void fetchContent(selectedDoc);
    }
  }, [selectedDoc, fetchContent]);

  const selectedInfo = documents.find((d) => d.filename === selectedDoc);

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
        {selectedDoc && (
          <a
            href={`${BACKEND_URL}/api/documents/${selectedDoc}/pdf`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--card)] px-4 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            <Download size={14} />
            Download PDF
          </a>
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

        {/* Main content area */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {loadingContent ? (
            <div className="flex flex-1 items-center justify-center">
              <Loader2
                size={24}
                className="animate-spin text-[var(--accent)]"
              />
            </div>
          ) : content != null ? (
            <div className="flex-1 overflow-y-auto px-8 py-6">
              {selectedInfo && (
                <div className="mb-6">
                  <h2 className="text-xl font-semibold text-[var(--foreground)]">
                    {selectedInfo.title || selectedInfo.filename}
                  </h2>
                  <p className="mt-1 text-xs text-[var(--muted)]">
                    {selectedInfo.filename} &middot;{" "}
                    {formatFileSize(selectedInfo.size)}
                  </p>
                </div>
              )}
              <article
                className="prose prose-sm max-w-none leading-7 prose-headings:text-[var(--foreground)] prose-p:text-[var(--foreground)] prose-strong:text-[var(--foreground)] prose-code:text-[var(--accent)] prose-a:text-[var(--accent)] prose-li:text-[var(--foreground)]"
              >
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {content}
                </ReactMarkdown>
              </article>
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center text-sm text-[var(--muted)]">
              Select a document to view its content.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
