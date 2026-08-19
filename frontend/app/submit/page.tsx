"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { conversationsApi } from "@/lib/api";
import { PLATFORMS, PLATFORM_LABELS } from "@/lib/constants";
import { useToast } from "@/hooks/useToast";
import Button from "@/components/shared/Button";
import Input from "@/components/shared/Input";
import Select from "@/components/shared/Select";
import Textarea from "@/components/shared/Textarea";

export default function SubmitPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const [platform, setPlatform] = useState("");
  const [postUrl, setPostUrl] = useState("");
  const [postAuthor, setPostAuthor] = useState("");
  const [originalPost, setOriginalPost] = useState("");
  const [fullThread, setFullThread] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!platform || !originalPost.trim()) {
      showToast("warning", "Platform and original post are required.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await conversationsApi.submitConversation({
        platform,
        post_url: postUrl || null,
        post_author: postAuthor || null,
        original_post: originalPost,
        full_thread: fullThread || null,
      });
      showToast("success", "Conversation submitted for analysis.");
      router.push(`/conversations/${result.conversation_id}`);
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Submission failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
        <Select
          id="platform"
          label="Platform *"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          placeholder="Select a platform"
          options={PLATFORMS.map((p) => ({ value: p, label: PLATFORM_LABELS[p] }))}
        />
        <Input
          id="post-url"
          label="Post URL"
          value={postUrl}
          onChange={(e) => setPostUrl(e.target.value)}
          placeholder="https://…"
        />
        <Input
          id="post-author"
          label="Post Author"
          value={postAuthor}
          onChange={(e) => setPostAuthor(e.target.value)}
          placeholder="Username of the original poster"
        />
        <Textarea
          id="original-post"
          label="Paste the original post here *"
          value={originalPost}
          onChange={(e) => setOriginalPost(e.target.value)}
          className="min-h-[140px]"
        />
        <Textarea
          id="full-thread"
          label="Paste the full thread including comments (optional but recommended)"
          value={fullThread}
          onChange={(e) => setFullThread(e.target.value)}
          className="min-h-[180px]"
        />

        <Button onClick={handleSubmit} loading={submitting} size="lg">
          Analyse This Conversation
        </Button>

        <p className="text-sm text-text-secondary">
          The system will analyse this conversation and generate response drafts in
          the background. This usually takes 15 to 30 seconds. You will see it
          appear in your feed once it is ready.
        </p>
      </div>
    </div>
  );
}
