"use client";

import { useState } from "react";
import { PLATFORMS, PLATFORM_LABELS } from "@/lib/constants";
import Button from "@/components/shared/Button";
import Input from "@/components/shared/Input";
import Select from "@/components/shared/Select";
import type { Community } from "./CommunityList";

export default function AddCommunityForm({
  onAdd,
}: {
  onAdd: (community: Omit<Community, "id">) => void;
}) {
  const [platform, setPlatform] = useState("");
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState("");

  const submit = () => {
    if (!platform || !name.trim()) return;
    onAdd({ platform, name: name.trim(), keywords: keywords.trim() });
    setName("");
    setKeywords("");
  };

  return (
    <div className="rounded-xl border border-border bg-surface p-6">
      <h2 className="text-lg font-medium text-text-primary">Add Community</h2>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Select
          label="Platform"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          placeholder="Select platform"
          options={PLATFORMS.map((p) => ({ value: p, label: PLATFORM_LABELS[p] }))}
        />
        <Input
          label="Community / Group Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. r/leadership"
        />
        <Input
          label="Keywords"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          placeholder="comma, separated, keywords"
        />
      </div>
      <Button className="mt-4" onClick={submit} disabled={!platform || !name.trim()}>
        Add Community
      </Button>
    </div>
  );
}
