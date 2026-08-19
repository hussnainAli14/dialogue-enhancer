"use client";

import { useState } from "react";
import { Database } from "lucide-react";
import { knowledgeApi } from "@/lib/api";
import type { Document, DocumentDetail } from "@/lib/types";
import { useKnowledge } from "@/hooks/useKnowledge";
import { useToast } from "@/hooks/useToast";
import StatsBar from "@/components/knowledge/StatsBar";
import UploadForm from "@/components/knowledge/UploadForm";
import DocumentList from "@/components/knowledge/DocumentList";
import Modal from "@/components/shared/Modal";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import LoadingSpinner from "@/components/shared/LoadingSpinner";
import EmptyState from "@/components/shared/EmptyState";
import ErrorState from "@/components/shared/ErrorState";

export default function KnowledgePage() {
  const { showToast } = useToast();
  const { data, loading, error, refetch, pollUntilProcessed } = useKnowledge();
  const [chunksDoc, setChunksDoc] = useState<DocumentDetail | null>(null);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    type: "delete" | "reindex";
    doc: Document;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const handleViewChunks = async (doc: Document) => {
    setChunksLoading(true);
    try {
      const detail = await knowledgeApi.getDocument(doc.id);
      setChunksDoc(detail);
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to load chunks");
    } finally {
      setChunksLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!confirmAction) return;
    setConfirmLoading(true);
    try {
      if (confirmAction.type === "delete") {
        await knowledgeApi.deleteDocument(confirmAction.doc.id);
        showToast("success", "Document deleted.");
      } else {
        await knowledgeApi.reindexDocument(confirmAction.doc.id);
        showToast("success", "Reindexing started.");
        pollUntilProcessed();
      }
      refetch(true);
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Action failed");
    } finally {
      setConfirmLoading(false);
      setConfirmAction(null);
    }
  };

  if (error && !data) {
    return (
      <ErrorState
        title="Could not load knowledge base"
        description={error}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div className="space-y-6">
      {data && (
        <StatsBar
          stats={{
            total_documents: data.total_documents,
            total_chunks: data.total_chunks,
            total_tokens: data.total_tokens,
          }}
        />
      )}

      <UploadForm
        onUploaded={() => {
          refetch(true);
          pollUntilProcessed();
        }}
      />

      {loading && !data ? (
        <div className="flex justify-center py-20">
          <LoadingSpinner size="lg" />
        </div>
      ) : (data?.documents.length ?? 0) === 0 ? (
        <EmptyState
          icon={<Database className="h-12 w-12" />}
          title="No documents yet"
          description="Upload your writing archive above to build the knowledge base that grounds every response."
        />
      ) : (
        <DocumentList
          documents={data!.documents}
          onViewChunks={handleViewChunks}
          onReindex={(doc) => setConfirmAction({ type: "reindex", doc })}
          onDelete={(doc) => setConfirmAction({ type: "delete", doc })}
        />
      )}

      {/* Chunks modal */}
      <Modal
        open={!!chunksDoc || chunksLoading}
        onClose={() => setChunksDoc(null)}
        title={chunksDoc ? `Chunks — ${chunksDoc.title || chunksDoc.filename}` : "Loading…"}
        wide
      >
        {chunksLoading ? (
          <div className="flex justify-center py-10">
            <LoadingSpinner size="lg" />
          </div>
        ) : (
          <div className="space-y-3">
            {chunksDoc?.chunks.map((chunk) => (
              <div
                key={chunk.id}
                className="rounded-lg border border-border bg-background p-4"
              >
                <p className="mb-1 text-xs text-text-muted">
                  Chunk {chunk.chunk_index + 1}
                  {chunk.token_count ? ` · ~${chunk.token_count} tokens` : ""}
                </p>
                <p className="text-sm text-text-primary whitespace-pre-wrap">
                  {chunk.content}
                </p>
              </div>
            ))}
          </div>
        )}
      </Modal>

      {/* Confirm dialog */}
      <ConfirmDialog
        open={!!confirmAction}
        title={confirmAction?.type === "delete" ? "Delete document?" : "Reindex document?"}
        description={
          confirmAction?.type === "delete"
            ? `This will permanently delete "${confirmAction.doc.title || confirmAction.doc.filename}" and all its chunks. This cannot be undone.`
            : `This will delete all existing chunks for "${confirmAction?.doc.title || confirmAction?.doc.filename}" and rebuild them from the original file.`
        }
        confirmLabel={confirmAction?.type === "delete" ? "Delete" : "Reindex"}
        destructive={confirmAction?.type === "delete"}
        loading={confirmLoading}
        onConfirm={handleConfirm}
        onCancel={() => setConfirmAction(null)}
      />
    </div>
  );
}
