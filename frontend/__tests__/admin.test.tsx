import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StatsCards } from "@/components/admin/stats-cards";
import { IngestionStatus } from "@/components/admin/ingestion-status";
import { UploadZone } from "@/components/admin/upload-zone";
import { DocumentTable } from "@/components/admin/document-table";
import { DocumentIndexingGuide } from "@/components/admin/document-indexing-guide";
import { StatusBadge } from "@/components/shared/status-badge";
import AdminDashboard from "@/app/admin/page";

const signOut = vi.fn();

vi.mock("next-auth/react", () => ({
  signOut: (...args: unknown[]) => signOut(...args),
}));

describe("admin components", () => {
  it("renders dashboard stats", () => {
    render(
      <StatsCards
        stats={{
          total_documents: 12,
          total_chunks: 345,
          total_conversations: 6,
          total_messages: 42,
          docs_by_status: { indexed: 10, failed: 2 },
        }}
      />,
    );

    expect(screen.getByText("Total Documents")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("345")).toBeInTheDocument();
    expect(screen.getByText("Healthy")).toBeInTheDocument();
  });

  it("renders status badge labels", () => {
    render(
      <div>
        <StatusBadge status="indexed" />
        <StatusBadge status="processing" />
        <StatusBadge status="failed" />
      </div>,
    );

    expect(screen.getByText("Indexed")).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("does not crash when ingestion status is forbidden", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ detail: "Role 'admin' required" }),
    }) as unknown as typeof fetch;

    render(<IngestionStatus />);

    expect(await screen.findByText("No active ingestion jobs")).toBeInTheDocument();
  });

  it("explains document indexing states clearly", () => {
    render(<DocumentIndexingGuide />);

    expect(screen.getByText("How indexing works")).toBeInTheDocument();
    expect(screen.getByText(/Users can upload and re-index their own documents/i)).toBeInTheDocument();
    expect(screen.getByText("File was accepted and queued for indexing.")).toBeInTheDocument();
    expect(screen.getByText("The document is searchable and chat can answer from it.")).toBeInTheDocument();
  });

  it("uploads selected file and calls completion callback", async () => {
    const onUploadComplete = vi.fn();
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ status: "indexed" }),
    }) as unknown as typeof fetch;

    render(<UploadZone onUploadComplete={onUploadComplete} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "sample.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(onUploadComplete).toHaveBeenCalled());
    expect(screen.getByText("sample.txt")).toBeInTheDocument();
    expect(screen.getByText("Indexed")).toBeInTheDocument();
  });

  it("uses the user-scoped document endpoint by default", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        total: 1,
        items: [
          {
            id: "doc-1",
            title: "User Guide",
            file_name: "guide.txt",
            file_type: "txt",
            file_size: 128,
            status: "indexed",
            total_chunks: 2,
            created_at: "2026-05-02T00:00:00Z",
          },
        ],
      }),
    }) as unknown as typeof fetch;

    render(<DocumentTable title="My documents" />);

    expect(await screen.findByText("User Guide")).toBeInTheDocument();
    expect(await screen.findByText("Ready for chat retrieval")).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/documents?"),
      expect.any(Object),
    );
  });

  it("starts a scoped chat from selected indexed documents", async () => {
    const onStartChat = vi.fn();
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        total: 2,
        items: [
          {
            id: "doc-1",
            title: "User Guide",
            file_name: "guide.txt",
            file_type: "txt",
            file_size: 128,
            status: "indexed",
            total_chunks: 2,
            created_at: "2026-05-02T00:00:00Z",
          },
          {
            id: "doc-2",
            title: "Pending Guide",
            file_name: "pending.txt",
            file_type: "txt",
            file_size: 64,
            status: "pending",
            total_chunks: 0,
            created_at: "2026-05-03T00:00:00Z",
          },
        ],
      }),
    }) as unknown as typeof fetch;

    render(<DocumentTable title="My documents" onStartChat={onStartChat} />);

    fireEvent.click(await screen.findByRole("checkbox", { name: /Use guide\.txt in chat/i }));
    fireEvent.click(screen.getByRole("button", { name: /Chat with selected doc/i }));

    expect(onStartChat).toHaveBeenCalledWith(["doc-1"]);
    expect(screen.getByRole("checkbox", { name: /Use pending\.txt in chat/i })).toBeDisabled();
  });

  it("does not mount admin polling when access is forbidden", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ detail: "Role 'admin' required" }),
    }) as unknown as typeof fetch;

    render(<AdminDashboard />);

    expect(await screen.findByText("Admin access required")).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });
});
