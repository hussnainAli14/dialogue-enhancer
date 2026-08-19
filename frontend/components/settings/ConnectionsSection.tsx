"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  Plug,
  RefreshCw,
} from "lucide-react";
import { connectionsApi } from "@/lib/api";
import type {
  AuthUrlResponse,
  ConnectionLog,
  PlatformConnectionStatus,
} from "@/lib/types";
import { PLATFORM_BADGE_CLASSES, PLATFORM_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useConnections } from "@/hooks/useConnections";
import { useToast } from "@/hooks/useToast";
import Button from "@/components/shared/Button";
import Input from "@/components/shared/Input";
import Modal from "@/components/shared/Modal";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import LoadingSpinner from "@/components/shared/LoadingSpinner";

const SUPPORTED = [
  "reddit",
  "bluesky",
  "mastodon",
  "discord",
  "telegram",
  "threads",
  "youtube",
];

const STATUS_STYLES: Record<string, string> = {
  connected: "bg-success/20 text-success",
  disconnected: "bg-text-muted/20 text-text-muted",
  error: "bg-danger/20 text-danger",
  expired: "bg-warning/20 text-warning",
};

const SETUP_INSTRUCTIONS: Record<string, string> = {
  discord:
    "Your bot must be added to each Discord server you want to monitor. Use the bot invite link shown when connecting, then add it to your servers.",
  telegram:
    "Your bot must be added to each Telegram channel or group you want to monitor as an admin. Contact the channel admin to add your bot.",
  youtube:
    "Your YouTube API quota is 10,000 units per day. The system stops fetching YouTube data if this limit is reached to avoid charges.",
};

function formatDate(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export default function ConnectionsSection() {
  const { connections, loading, refetch } = useConnections();
  const { showToast } = useToast();

  const [busy, setBusy] = useState<string | null>(null);
  const [blueskyOpen, setBlueskyOpen] = useState(false);
  const [telegramOpen, setTelegramOpen] = useState(false);
  const [telegramMeta, setTelegramMeta] = useState<AuthUrlResponse | null>(null);
  const [bskyHandle, setBskyHandle] = useState("");
  const [bskyPassword, setBskyPassword] = useState("");
  const [disconnectTarget, setDisconnectTarget] = useState<string | null>(null);
  const [errorModal, setErrorModal] = useState<{ platform: string; message: string } | null>(null);

  const byPlatform = new Map(connections.map((c) => [c.platform, c]));

  const handleConnect = async (platform: string) => {
    setBusy(platform);
    try {
      const res = await connectionsApi.getAuthUrl(platform);
      if (res.method === "oauth" && res.auth_url) {
        window.location.href = res.auth_url; // redirect to platform
        return;
      }
      if (platform === "bluesky") {
        setBlueskyOpen(true);
      } else if (platform === "telegram") {
        setTelegramMeta(res);
        setTelegramOpen(true);
      }
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Could not start connect");
    } finally {
      setBusy(null);
    }
  };

  const submitBluesky = async () => {
    setBusy("bluesky");
    try {
      const res = await connectionsApi.connectBluesky(bskyHandle.trim(), bskyPassword);
      showToast("success", `Bluesky connected as ${res.account_name}`);
      setBlueskyOpen(false);
      setBskyHandle("");
      setBskyPassword("");
      refetch();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Bluesky connect failed");
    } finally {
      setBusy(null);
    }
  };

  const connectTelegram = async () => {
    setBusy("telegram");
    try {
      const res = await connectionsApi.connectTelegram();
      showToast("success", `Telegram bot connected: ${res.account_name}`);
      setTelegramOpen(false);
      refetch();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Telegram connect failed");
    } finally {
      setBusy(null);
    }
  };

  const handleTest = async (platform: string) => {
    setBusy(platform);
    try {
      const res = await connectionsApi.validate(platform);
      if (res.valid) {
        showToast("success", `${PLATFORM_LABELS[platform]} connection is valid.`);
      } else {
        showToast("error", `${PLATFORM_LABELS[platform]} connection is not valid. Reconnect it.`);
        refetch();
      }
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Test failed");
    } finally {
      setBusy(null);
    }
  };

  const confirmDisconnect = async () => {
    if (!disconnectTarget) return;
    const platform = disconnectTarget;
    setBusy(platform);
    try {
      await connectionsApi.disconnect(platform);
      showToast("success", `${PLATFORM_LABELS[platform]} disconnected.`);
      refetch();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Disconnect failed");
    } finally {
      setBusy(null);
      setDisconnectTarget(null);
    }
  };

  return (
    <section id="connections" className="scroll-mt-6 space-y-4">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-medium text-text-primary">
          <Plug className="h-5 w-5 text-accent-light" />
          Platform Connections
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Connect your social media accounts so the system can monitor
          conversations and post approved responses automatically.
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center py-10">
          <LoadingSpinner size="lg" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {SUPPORTED.map((platform) => {
            const c: PlatformConnectionStatus | undefined = byPlatform.get(platform);
            const status = c?.status ?? "disconnected";
            const isBusy = busy === platform;
            return (
              <div
                key={platform}
                className="rounded-xl border border-border bg-surface p-6"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "rounded px-2 py-0.5 text-xs font-medium",
                        PLATFORM_BADGE_CLASSES[platform]
                      )}
                    >
                      {PLATFORM_LABELS[platform]}
                    </span>
                  </div>
                  <span
                    className={cn(
                      "rounded px-2 py-0.5 text-xs font-medium capitalize",
                      STATUS_STYLES[status]
                    )}
                  >
                    {status}
                  </span>
                </div>

                <div className="mt-3 min-h-[2.5rem] text-sm">
                  {status === "connected" || status === "expired" ? (
                    <>
                      <p className="text-text-primary">
                        Connected as {c?.account_name ?? "—"}
                      </p>
                      {c?.connected_at && (
                        <p className="text-xs text-text-muted">
                          Since {formatDate(c.connected_at)}
                        </p>
                      )}
                    </>
                  ) : status === "error" ? (
                    <p className="text-xs text-danger">
                      {c?.last_error ?? "Connection error."}
                    </p>
                  ) : (
                    <p className="text-xs text-text-muted">Not connected.</p>
                  )}
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {status === "disconnected" && (
                    <Button size="sm" onClick={() => handleConnect(platform)} loading={isBusy}>
                      Connect
                    </Button>
                  )}
                  {(status === "connected" || status === "expired") && (
                    <>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleTest(platform)}
                        loading={isBusy}
                      >
                        Test Connection
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-danger"
                        onClick={() => setDisconnectTarget(platform)}
                      >
                        Disconnect
                      </Button>
                    </>
                  )}
                  {status === "error" && (
                    <>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleConnect(platform)}
                        loading={isBusy}
                      >
                        Reconnect
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          setErrorModal({
                            platform,
                            message: c?.last_error ?? "Unknown error.",
                          })
                        }
                      >
                        View Error
                      </Button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <SetupInstructions />
      <ConnectionLogs />

      {/* Bluesky modal */}
      <Modal open={blueskyOpen} onClose={() => setBlueskyOpen(false)} title="Connect Bluesky">
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Bluesky uses an app password, not your main password. Create one at{" "}
            <span className="text-accent-light">bsky.app/settings/app-passwords</span>.
          </p>
          <Input
            id="bsky-handle"
            label="Bluesky Handle"
            placeholder="yourname.bsky.social"
            value={bskyHandle}
            onChange={(e) => setBskyHandle(e.target.value)}
          />
          <Input
            id="bsky-password"
            label="App Password"
            type="password"
            placeholder="xxxx-xxxx-xxxx-xxxx"
            value={bskyPassword}
            onChange={(e) => setBskyPassword(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setBlueskyOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={submitBluesky}
              loading={busy === "bluesky"}
              disabled={!bskyHandle.trim() || !bskyPassword}
            >
              Connect
            </Button>
          </div>
        </div>
      </Modal>

      {/* Telegram modal */}
      <Modal open={telegramOpen} onClose={() => setTelegramOpen(false)} title="Connect Telegram">
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Telegram connects using the bot token configured in the server
            environment. The bot must be added to each channel or group you want
            to monitor as an admin.
          </p>
          {telegramMeta?.metadata?.bot_username ? (
            <p className="text-sm text-text-primary">
              Bot: @{String(telegramMeta.metadata.bot_username)}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setTelegramOpen(false)}>
              Cancel
            </Button>
            <Button onClick={connectTelegram} loading={busy === "telegram"}>
              Validate & Connect
            </Button>
          </div>
        </div>
      </Modal>

      {/* Error modal */}
      <Modal
        open={!!errorModal}
        onClose={() => setErrorModal(null)}
        title={errorModal ? `${PLATFORM_LABELS[errorModal.platform]} error` : ""}
      >
        <p className="whitespace-pre-wrap break-words text-sm text-danger">
          {errorModal?.message}
        </p>
      </Modal>

      <ConfirmDialog
        open={!!disconnectTarget}
        title={`Disconnect ${disconnectTarget ? PLATFORM_LABELS[disconnectTarget] : ""}?`}
        description="The system will no longer be able to monitor this platform until you reconnect."
        confirmLabel="Disconnect"
        destructive
        loading={!!busy && busy === disconnectTarget}
        onConfirm={confirmDisconnect}
        onCancel={() => setDisconnectTarget(null)}
      />
    </section>
  );
}

function SetupInstructions() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-border bg-surface">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between p-4 text-sm font-medium text-text-primary"
      >
        Setup Instructions
        <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-3 border-t border-border p-4 text-sm">
          {Object.entries(SETUP_INSTRUCTIONS).map(([platform, text]) => (
            <div key={platform}>
              <p className="font-medium text-text-primary">{PLATFORM_LABELS[platform]}</p>
              <p className="text-text-secondary">{text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ConnectionLogs() {
  const [open, setOpen] = useState(false);
  const [logs, setLogs] = useState<ConnectionLog[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await connectionsApi.getLogs();
      setLogs(res.logs.slice(0, 10));
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!open) {
      if (timer.current) clearInterval(timer.current);
      return;
    }
    load();
    timer.current = setInterval(load, 30000);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [open, load]);

  return (
    <div className="rounded-xl border border-border bg-surface">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between p-4 text-sm font-medium text-text-primary"
      >
        <span className="flex items-center gap-2">
          Recent Connection Events
          {open && <RefreshCw className="h-3 w-3 text-text-muted" />}
        </span>
        <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="border-t border-border p-4">
          {logs.length === 0 ? (
            <p className="text-sm text-text-muted">No events yet.</p>
          ) : (
            <ul className="space-y-2 text-xs">
              {logs.map((log) => (
                <li key={log.id} className="flex items-start gap-2">
                  <span className="font-medium text-text-secondary capitalize">
                    {log.platform}
                  </span>
                  <span className="text-accent-light">{log.event}</span>
                  <span className="flex-1 text-text-muted">{log.message}</span>
                  <span className="text-text-muted">
                    {new Date(log.created_at).toLocaleTimeString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
