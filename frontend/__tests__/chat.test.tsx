import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatPage from "@/app/chat/page";

import { ChatInput } from "@/components/chat/chat-input";
import { MessageBubble } from "@/components/chat/message-bubble";
import { SourceCitation } from "@/components/chat/source-citation";
import { SourcesPanel } from "@/components/chat/sources-panel";
import { ThinkingIndicator } from "@/components/chat/thinking-indicator";
import { ChatSidebar } from "@/components/chat/chat-sidebar";

const signOut = vi.fn();
const replace = vi.fn();
let searchParams = new URLSearchParams();
const confirmMock = vi.fn(() => true);

vi.mock("next-auth/react", () => ({
  signOut: (...args: unknown[]) => signOut(...args),
  useSession: () => ({
    data: {
      roles: ["admin"],
      user: { email: "admin@example.com", roles: ["admin"] },
    },
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => searchParams,
}));

describe("chat components", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    searchParams = new URLSearchParams();
    vi.stubGlobal("confirm", confirmMock);
    confirmMock.mockReturnValue(true);
  });

  it("renders user and assistant messages", () => {
    render(
      <div>
        <MessageBubble
          message={{ id: "1", role: "user", content: "Hello" }}
          onCitationClick={vi.fn()}
        />
        <MessageBubble
          message={{ id: "2", role: "assistant", content: "Answer [1]" }}
          onCitationClick={vi.fn()}
        />
      </div>,
    );

    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("Answer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Source 1" })).toBeInTheDocument();
  });

  it("renders clickable citations inside markdown list items", () => {
    render(
      <MessageBubble
        message={{
          id: "3",
          role: "assistant",
          content: "- Main point [2]\n- Supporting point [3]",
        }}
        onCitationClick={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Source 2" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Source 3" })).toBeInTheDocument();
  });

  it("sends trimmed message on Enter", () => {
    const onSend = vi.fn();
    render(
      <ChatInput
        onSend={onSend}
        responseMode="strict_documents"
        onResponseModeChange={vi.fn()}
      />,
    );

    const input = screen.getByPlaceholderText(
      "Ask about your documents. Outside knowledge is off by default.",
    );
    fireEvent.change(input, { target: { value: "  What is RAG?  " } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onSend).toHaveBeenCalledWith("What is RAG?", "strict_documents");
    expect(input).toHaveValue("");
  });

  it("keeps newline behavior for Shift+Enter", () => {
    const onSend = vi.fn();
    render(
      <ChatInput
        onSend={onSend}
        responseMode="strict_documents"
        onResponseModeChange={vi.fn()}
      />,
    );

    const input = screen.getByPlaceholderText(
      "Ask about your documents. Outside knowledge is off by default.",
    );
    fireEvent.change(input, { target: { value: "Line one" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });

    expect(onSend).not.toHaveBeenCalled();
    expect(input).toHaveValue("Line one");
  });

  it("fires citation click callback", () => {
    const onClick = vi.fn();
    render(<SourceCitation number={3} onClick={onClick} />);

    fireEvent.click(screen.getByRole("button", { name: "Source 3" }));

    expect(onClick).toHaveBeenCalledWith(3);
  });

  it("renders source excerpts in the sources panel", () => {
    render(
      <SourcesPanel
        sources={[
          {
            citation_number: 1,
            document_title: "Alpha Guide",
            file_name: "alpha.txt",
            page_number: 2,
            section: "Overview",
            section_path: "Alpha Guide > Method > Overview",
            block_type: "method",
            score: 0.87,
            excerpt: "Hybrid retrieval combines vector similarity with BM25 keyword search.",
            selection_reason: "method evidence from Alpha Guide > Method > Overview",
            answer_section: "method",
          },
        ]}
        activeCitation={1}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Evidence snippet")).toBeInTheDocument();
    expect(
      screen.getByText(/Hybrid retrieval combines vector similarity with BM25 keyword search/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Evidence score 0.87/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Alpha Guide > Method > Overview/i).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/method evidence from Alpha Guide > Method > Overview/i),
    ).toBeInTheDocument();
  });

  it("renders thinking indicator", () => {
    render(<ThinkingIndicator />);

    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument();
  });

  it("uploads documents from the paperclip control", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        id: "doc-1",
        title: "sample",
        file_name: "sample.txt",
        file_type: "txt",
        file_size: 7,
        status: "indexed",
        total_chunks: 1,
        created_at: "2026-05-04T00:00:00Z",
        updated_at: "2026-05-04T00:00:00Z",
      }),
    }) as unknown as typeof fetch;

    render(
      <ChatInput
        onSend={vi.fn()}
        responseMode="strict_documents"
        onResponseModeChange={vi.fn()}
      />,
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "sample.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/v1/documents/upload",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(await screen.findByText("sample.txt")).toBeInTheDocument();
    expect(await screen.findByText("Indexed")).toBeInTheDocument();
  });

  it("shows strict mode by default and lets the user switch to hybrid mode", () => {
    const onResponseModeChange = vi.fn();
    render(
      <ChatInput
        onSend={vi.fn()}
        responseMode="strict_documents"
        onResponseModeChange={onResponseModeChange}
      />,
    );

    expect(screen.getByRole("button", { name: "Document only" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Allow outside knowledge" }));
    expect(onResponseModeChange).toHaveBeenCalledWith("hybrid_general");
  });

  it("renders navigation to chat, documents, and admin dashboard for admins", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        items: [
          {
            id: "conv-1",
            title: "Old chat",
            updated_at: "2026-05-04T00:00:00Z",
            message_count: 2,
          },
        ],
      }),
    }) as unknown as typeof fetch;

    render(<ChatSidebar open onToggle={vi.fn()} />);

    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("href", "/chat");
    expect(screen.getByRole("link", { name: "My documents" })).toHaveAttribute("href", "/documents");
    expect(screen.getByRole("link", { name: "Admin dashboard" })).toHaveAttribute("href", "/admin");
    expect(screen.getByRole("link", { name: "New chat" })).toHaveAttribute("href", "/chat");
    expect(await screen.findByRole("link", { name: /Old chat/i })).toHaveAttribute(
      "href",
      "/chat?conversationId=conv-1",
    );
  });

  it("deletes a conversation from the sidebar and returns to empty chat when it was active", async () => {
    searchParams = new URLSearchParams("conversationId=conv-1");
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          items: [
            {
              id: "conv-1",
              title: "Old chat",
              updated_at: "2026-05-04T00:00:00Z",
              message_count: 2,
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 204,
      }) as unknown as typeof fetch;

    render(<ChatSidebar open onToggle={vi.fn()} />);

    expect(await screen.findByRole("link", { name: /Old chat/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Mở menu đoạn chat Old chat/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Xóa đoạn chat" }));

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/v1/conversations/conv-1",
        expect.objectContaining({ method: "DELETE", credentials: "same-origin" }),
      ),
    );
    await waitFor(() => expect(screen.queryByText("Old chat")).not.toBeInTheDocument());
    expect(replace).toHaveBeenCalledWith("/chat");
  });

  it("renames a conversation from the sidebar overflow menu", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          items: [
            {
              id: "conv-1",
              title: "Old chat",
              updated_at: "2026-05-04T00:00:00Z",
              message_count: 2,
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: "conv-1",
          title: "Renamed chat",
          created_at: "2026-05-04T00:00:00Z",
          updated_at: "2026-05-04T00:00:02Z",
          message_count: 2,
          active_documents: [],
        }),
      }) as unknown as typeof fetch;

    render(<ChatSidebar open onToggle={vi.fn()} />);

    expect(await screen.findByRole("link", { name: /Old chat/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Mở menu đoạn chat Old chat/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Đổi tên đoạn chat" }));

    const renameInput = await screen.findByRole("textbox", {
      name: /Rename conversation Old chat/i,
    });
    fireEvent.change(renameInput, { target: { value: "Renamed chat" } });
    fireEvent.keyDown(renameInput, { key: "Enter" });

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/v1/conversations/conv-1",
        expect.objectContaining({ method: "PATCH", credentials: "same-origin" }),
      ),
    );
    expect(await screen.findByText("Renamed chat")).toBeInTheDocument();
  });

  it("logs out through the authenticated shell footer", () => {
    globalThis.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;

    render(<ChatSidebar open onToggle={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Logout" }));

    expect(signOut).toHaveBeenCalledWith({ callbackUrl: "/login" });
  });

  it("loads stored messages for the selected conversation", async () => {
    searchParams = new URLSearchParams("conversationId=conv-123");
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ([
          { id: "m1", role: "user", content: "Question" },
          { id: "m2", role: "assistant", content: "Answer" },
        ]),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: "conv-123",
          title: "Scoped chat",
          created_at: "2026-05-04T00:00:00Z",
          updated_at: "2026-05-04T00:00:00Z",
          message_count: 2,
          active_documents: [
            {
              id: "doc-1",
              title: "Alpha Guide",
              file_name: "alpha.txt",
              status: "indexed",
              total_chunks: 2,
            },
          ],
        }),
      }) as unknown as typeof fetch;

    render(<ChatPage />);

    expect(await screen.findByText("Question")).toBeInTheDocument();
    expect(await screen.findByText("Answer")).toBeInTheDocument();
    expect(await screen.findByText(/Using 1 active document/i)).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/v1/conversations/conv-123/messages",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("drops a stale conversation id from the URL when the conversation no longer exists", async () => {
    searchParams = new URLSearchParams("conversationId=missing-conv");
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: "Conversation not found" }),
      }) as unknown as typeof fetch;

    render(<ChatPage />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat"));
    expect(screen.queryByText("Conversation not found")).not.toBeInTheDocument();
  });

  it("adds a professional upload notice into the chat thread", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({
          id: "doc-1",
          title: "sample",
          file_name: "sample.txt",
          file_type: "txt",
          file_size: 7,
          status: "pending",
          total_chunks: 0,
          created_at: "2026-05-04T00:00:00Z",
          updated_at: "2026-05-04T00:00:00Z",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: "doc-1",
          title: "sample",
          file_name: "sample.txt",
          file_type: "txt",
          file_size: 7,
          status: "indexed",
          total_chunks: 1,
          created_at: "2026-05-04T00:00:00Z",
          updated_at: "2026-05-04T00:00:01Z",
          duplicate_of_existing: false,
          error_message: null,
        }),
      }) as unknown as typeof fetch;

    render(<ChatPage />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "sample.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText(/Uploaded sample\.txt/i)).toBeInTheDocument();
    expect(
      await screen.findByText(/become searchable as soon as indexing completes/i),
    ).toBeInTheDocument();
  });

  it("marks duplicate uploads clearly in chat", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "doc-1",
        title: "sample",
        file_name: "sample.txt",
        file_type: "txt",
        file_size: 7,
        status: "indexed",
        total_chunks: 1,
        created_at: "2026-05-04T00:00:00Z",
        updated_at: "2026-05-04T00:00:00Z",
        duplicate_of_existing: true,
      }),
    }) as unknown as typeof fetch;

    render(<ChatPage />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "sample.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText(/already in your document library/i)).toBeInTheDocument();
    expect(await screen.findByText(/sample\.txt \(already uploaded\)/i)).toBeInTheDocument();
  });

  it("sends selected document ids with the next chat request", async () => {
    searchParams = new URLSearchParams("documentIds=doc-1,doc-2");
    const encoder = new TextEncoder();

    globalThis.fetch = vi.fn(async (input, init) => {
      const url = String(input);
      if (url === "/api/v1/documents/doc-1") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: "doc-1",
            title: "Alpha Guide",
            file_name: "alpha.txt",
            status: "indexed",
            total_chunks: 2,
          }),
        } as Response;
      }
      if (url === "/api/v1/documents/doc-2") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: "doc-2",
            title: "Beta Guide",
            file_name: "beta.txt",
            status: "indexed",
            total_chunks: 4,
          }),
        } as Response;
      }
      if (url === "/api/v1/chat") {
        return {
          ok: true,
          status: 200,
          body: {
            getReader: () => {
              let done = false;
              return {
                read: async () => {
                  if (done) return { done: true, value: undefined };
                  done = true;
                  return {
                    done: false,
                    value: encoder.encode(
                      'data: {"type":"chunk","content":"Scoped answer"}\n\n' +
                        'data: {"type":"done","message_id":"msg-1","conversation_id":"conv-1","active_documents":[{"id":"doc-1","title":"Alpha Guide","file_name":"alpha.txt","status":"indexed","total_chunks":2},{"id":"doc-2","title":"Beta Guide","file_name":"beta.txt","status":"indexed","total_chunks":4}]}\n\n',
                    ),
                  };
                },
              };
            },
          },
        } as Response;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }) as unknown as typeof fetch;

    render(<ChatPage />);

    expect(await screen.findByText(/Using 2 active documents/i)).toBeInTheDocument();

    const input = screen.getByPlaceholderText(
      "Ask about your documents. Outside knowledge is off by default.",
    );
    fireEvent.change(input, { target: { value: "Compare the two files" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/v1/chat",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    const chatCall = vi.mocked(globalThis.fetch).mock.calls.find(
      ([url]) => String(url) === "/api/v1/chat",
    );
    expect(chatCall).toBeTruthy();
    expect(JSON.parse(String(chatCall?.[1]?.body))).toMatchObject({
      query: "Compare the two files",
      document_ids: ["doc-1", "doc-2"],
      response_mode: "strict_documents",
    });
  });

  it("sends hybrid_general only when the mode is explicitly enabled", async () => {
    const encoder = new TextEncoder();

    globalThis.fetch = vi.fn(async (input, init) => {
      const url = String(input);
      if (url === "/api/v1/chat") {
        return {
          ok: true,
          status: 200,
          body: {
            getReader: () => {
              let done = false;
              return {
                read: async () => {
                  if (done) return { done: true, value: undefined };
                  done = true;
                  return {
                    done: false,
                    value: encoder.encode(
                      'data: {"type":"chunk","content":"Hybrid answer"}\n\n' +
                        'data: {"type":"done","message_id":"msg-2","conversation_id":"conv-2","active_documents":[]}\n\n',
                    ),
                  };
                },
              };
            },
          },
        } as Response;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }) as unknown as typeof fetch;

    render(<ChatPage />);

    fireEvent.click(screen.getByRole("button", { name: "Allow outside knowledge" }));

    const input = screen.getByPlaceholderText(
      "Ask anything. I will use your documents first, then outside knowledge if needed.",
    );
    fireEvent.change(input, { target: { value: "What is machine learning?" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/v1/chat",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    const chatCall = vi.mocked(globalThis.fetch).mock.calls.find(
      ([url]) => String(url) === "/api/v1/chat",
    );
    expect(JSON.parse(String(chatCall?.[1]?.body))).toMatchObject({
      query: "What is machine learning?",
      response_mode: "hybrid_general",
    });
  });

  it("deletes a message pair from the loaded conversation without reloading it", async () => {
    searchParams = new URLSearchParams("conversationId=conv-123");
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ([
          { id: "m1", role: "user", content: "Question" },
          { id: "m2", role: "assistant", content: "Answer" },
          { id: "m3", role: "user", content: "Another question" },
          { id: "m4", role: "assistant", content: "Another answer" },
        ]),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: "conv-123",
          title: "Scoped chat",
          created_at: "2026-05-04T00:00:00Z",
          updated_at: "2026-05-04T00:00:00Z",
          message_count: 4,
          active_documents: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 204,
      }) as unknown as typeof fetch;

    render(<ChatPage />);

    expect(await screen.findByText("Question")).toBeInTheDocument();
    expect(screen.getByText("Answer")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Mở menu tin nhắn người dùng" })[0]);
    fireEvent.click(await screen.findByRole("menuitem", { name: "Xóa đoạn chat" }));

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/v1/conversations/conv-123/messages/m1",
        expect.objectContaining({ method: "DELETE", credentials: "same-origin" }),
      ),
    );
    await waitFor(() => {
      expect(screen.queryByText("Question")).not.toBeInTheDocument();
      expect(screen.queryByText("Answer")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Another question")).toBeInTheDocument();
    expect(screen.getByText("Another answer")).toBeInTheDocument();
  });

  it("deletes a freshly sent exchange using the server user message id from SSE", async () => {
    searchParams = new URLSearchParams("conversationId=conv-123");
    const encoder = new TextEncoder();

    globalThis.fetch = vi.fn(async (input) => {
      const url = String(input);
      if (url === "/api/v1/conversations/conv-123/messages") {
        return {
          ok: true,
          status: 200,
          json: async () => [],
        } as Response;
      }
      if (url === "/api/v1/conversations/conv-123") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: "conv-123",
            title: "Scoped chat",
            created_at: "2026-05-04T00:00:00Z",
            updated_at: "2026-05-04T00:00:00Z",
            message_count: 0,
            active_documents: [],
          }),
        } as Response;
      }
      if (url === "/api/v1/chat") {
        return {
          ok: true,
          status: 200,
          body: {
            getReader: () => {
              let done = false;
              return {
                read: async () => {
                  if (done) return { done: true, value: undefined };
                  done = true;
                  return {
                    done: false,
                    value: encoder.encode(
                      'data: {"type":"chunk","content":"Fresh answer"}\n\n' +
                        'data: {"type":"done","user_message_id":"srv-user-5","message_id":"srv-assistant-5","conversation_id":"conv-123","active_documents":[]}\n\n',
                    ),
                  };
                },
              };
            },
          },
        } as Response;
      }
      if (url === "/api/v1/conversations/conv-123/messages/srv-user-5") {
        return { ok: true, status: 204 } as Response;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }) as unknown as typeof fetch;

    render(<ChatPage />);

    const input = screen.getByPlaceholderText(
      "Ask about your documents. Outside knowledge is off by default.",
    );
    fireEvent.change(input, { target: { value: "Fresh question" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(await screen.findByText("Fresh answer")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: /menu tin/i })[0]);
    fireEvent.click(await screen.findByRole("menuitem", { name: /Xóa đoạn chat|XÃ³a Ä‘oáº¡n chat/i }));

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/v1/conversations/conv-123/messages/srv-user-5",
        expect.objectContaining({ method: "DELETE", credentials: "same-origin" }),
      ),
    );
  });

  it("edits a user message, deletes the old exchange, and sends the replacement question", async () => {
    searchParams = new URLSearchParams("conversationId=conv-123");
    const encoder = new TextEncoder();

    globalThis.fetch = vi.fn(async (input, init) => {
      const url = String(input);
      if (url === "/api/v1/conversations/conv-123/messages") {
        return {
          ok: true,
          status: 200,
          json: async () => ([
            { id: "m1", role: "user", content: "Question" },
            { id: "m2", role: "assistant", content: "Answer" },
          ]),
        } as Response;
      }
      if (url === "/api/v1/conversations/conv-123") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: "conv-123",
            title: "Scoped chat",
            created_at: "2026-05-04T00:00:00Z",
            updated_at: "2026-05-04T00:00:00Z",
            message_count: 2,
            active_documents: [],
          }),
        } as Response;
      }
      if (url === "/api/v1/chat") {
        return {
          ok: true,
          status: 200,
          body: {
            getReader: () => {
              let done = false;
              return {
                read: async () => {
                  if (done) return { done: true, value: undefined };
                  done = true;
                  return {
                    done: false,
                    value: encoder.encode(
                      'data: {"type":"chunk","content":"Updated answer"}\n\n' +
                        'data: {"type":"done","user_message_id":"srv-user-3","message_id":"msg-3","conversation_id":"conv-123","active_documents":[]}\n\n',
                    ),
                  };
                },
              };
            },
          },
        } as Response;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }) as unknown as typeof fetch;

    render(<ChatPage />);

    expect(await screen.findByText("Question")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /menu tin/i })[0]);
    fireEvent.click(await screen.findByRole("menuitem", { name: /gửi lại/i }));

    const input = screen.getByPlaceholderText(
      "Ask about your documents. Outside knowledge is off by default.",
    );
    expect(input).toHaveValue("Question");
    expect(screen.getByRole("button", { name: "Resend edited message" })).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "Updated question" } });
    fireEvent.keyDown(input, { key: "Enter" });

    const chatCall = vi.mocked(globalThis.fetch).mock.calls.find(
      ([url]) => String(url) === "/api/v1/chat",
    );
    expect(JSON.parse(String(chatCall?.[1]?.body))).toMatchObject({
      query: "Updated question",
      conversation_id: "conv-123",
      replace_message_id: "m1",
      response_mode: "strict_documents",
    });
    expect(
      vi.mocked(globalThis.fetch).mock.calls.some(
        ([url]) => String(url) === "/api/v1/conversations/conv-123/messages/m1",
      ),
    ).toBe(false);
    await waitFor(() => {
      expect(screen.getByText("Updated question")).toBeInTheDocument();
      expect(screen.getByText("Updated answer")).toBeInTheDocument();
    });
  });

  it("regenerates an assistant answer from the previous user prompt", async () => {
    searchParams = new URLSearchParams("conversationId=conv-123");
    const encoder = new TextEncoder();

    globalThis.fetch = vi.fn(async (input) => {
      const url = String(input);
      if (url === "/api/v1/conversations/conv-123/messages") {
        return {
          ok: true,
          status: 200,
          json: async () => ([
            { id: "m1", role: "user", content: "Original question" },
            { id: "m2", role: "assistant", content: "Original answer" },
          ]),
        } as Response;
      }
      if (url === "/api/v1/conversations/conv-123") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: "conv-123",
            title: "Scoped chat",
            created_at: "2026-05-04T00:00:00Z",
            updated_at: "2026-05-04T00:00:00Z",
            message_count: 2,
            active_documents: [],
          }),
        } as Response;
      }
      if (url === "/api/v1/chat") {
        return {
          ok: true,
          status: 200,
          body: {
            getReader: () => {
              let done = false;
              return {
                read: async () => {
                  if (done) return { done: true, value: undefined };
                  done = true;
                  return {
                    done: false,
                    value: encoder.encode(
                      'data: {"type":"chunk","content":"Regenerated answer"}\n\n' +
                        'data: {"type":"done","user_message_id":"srv-user-4","message_id":"msg-4","conversation_id":"conv-123","active_documents":[]}\n\n',
                    ),
                  };
                },
              };
            },
          },
        } as Response;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }) as unknown as typeof fetch;

    render(<ChatPage />);

    expect(await screen.findByText("Original answer")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /menu tin/i })[1]);
    fireEvent.click(await screen.findByRole("menuitem", { name: /Tạo lại|Táº¡o láº¡i/i }));

    const input = screen.getByPlaceholderText(
      "Ask about your documents. Outside knowledge is off by default.",
    );
    expect(input).toHaveValue("Original question");

    fireEvent.keyDown(input, { key: "Enter" });

    const chatCall = vi.mocked(globalThis.fetch).mock.calls.find(
      ([url]) => String(url) === "/api/v1/chat",
    );
    expect(JSON.parse(String(chatCall?.[1]?.body))).toMatchObject({
      query: "Original question",
      conversation_id: "conv-123",
      replace_message_id: "m2",
    });
    expect(await screen.findByText("Regenerated answer")).toBeInTheDocument();
  });

  it("restores the original exchange when edit-and-resend fails", async () => {
    searchParams = new URLSearchParams("conversationId=conv-123");
    globalThis.fetch = vi.fn(async (input) => {
      const url = String(input);
      if (url === "/api/v1/conversations/conv-123/messages") {
        return {
          ok: true,
          status: 200,
          json: async () => ([
            { id: "m1", role: "user", content: "Question" },
            { id: "m2", role: "assistant", content: "Answer" },
          ]),
        } as Response;
      }
      if (url === "/api/v1/conversations/conv-123") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: "conv-123",
            title: "Scoped chat",
            created_at: "2026-05-04T00:00:00Z",
            updated_at: "2026-05-04T00:00:00Z",
            message_count: 2,
            active_documents: [],
          }),
        } as Response;
      }
      if (url === "/api/v1/chat") {
        return {
          ok: false,
          status: 503,
          json: async () => ({ detail: "Chat request failed" }),
        } as Response;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }) as unknown as typeof fetch;

    render(<ChatPage />);

    expect(await screen.findByText("Question")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /menu tin/i })[0]);
    fireEvent.click(await screen.findByRole("menuitem", { name: /gửi lại/i }));

    const input = screen.getByPlaceholderText(
      "Ask about your documents. Outside knowledge is off by default.",
    );
    fireEvent.change(input, { target: { value: "Updated question" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(await screen.findByText("Question")).toBeInTheDocument();
    expect(screen.getByText("Answer")).toBeInTheDocument();
    expect(screen.getByText(/Message action failed:/i)).toBeInTheDocument();
    expect(screen.getByText(/Chat request failed/i)).toBeInTheDocument();
    expect(input).toHaveValue("Updated question");
  });

  it("cancels edit mode and clears the composer draft", async () => {
    searchParams = new URLSearchParams("conversationId=conv-123");
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ([
          { id: "m1", role: "user", content: "Question" },
          { id: "m2", role: "assistant", content: "Answer" },
        ]),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: "conv-123",
          title: "Scoped chat",
          created_at: "2026-05-04T00:00:00Z",
          updated_at: "2026-05-04T00:00:00Z",
          message_count: 2,
          active_documents: [],
        }),
      }) as unknown as typeof fetch;

    render(<ChatPage />);

    expect(await screen.findByText("Question")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /menu tin/i })[0]);
    fireEvent.click(await screen.findByRole("menuitem", { name: /gửi lại/i }));

    const input = screen.getByPlaceholderText(
      "Ask about your documents. Outside knowledge is off by default.",
    );
    expect(input).toHaveValue("Question");

    fireEvent.click(screen.getByRole("button", { name: /Hủy|Há»§y/i }));

    expect(screen.queryByRole("button", { name: "Resend edited message" })).not.toBeInTheDocument();
    expect(input).toHaveValue("");
  });

  it("copies an assistant answer and shows a local success notice", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(globalThis.navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    render(
      <MessageBubble
        message={{ id: "2", role: "assistant", content: "Answer [1]" }}
        onCitationClick={vi.fn()}
        onCopy={async (content) => {
          await navigator.clipboard.writeText(content);
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /menu tin/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Sao chép|Sao chÃ©p/i }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Answer [1]"));
  });

  it("shows a message-action error when copying fails", async () => {
    searchParams = new URLSearchParams("conversationId=conv-123");
    const writeText = vi.fn().mockRejectedValue(new Error("Clipboard denied"));
    Object.defineProperty(globalThis.navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ([
          { id: "m1", role: "user", content: "Question" },
          { id: "m2", role: "assistant", content: "Answer" },
        ]),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: "conv-123",
          title: "Scoped chat",
          created_at: "2026-05-04T00:00:00Z",
          updated_at: "2026-05-04T00:00:00Z",
          message_count: 2,
          active_documents: [],
        }),
      }) as unknown as typeof fetch;

    render(<ChatPage />);

    expect(await screen.findByText("Answer")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /menu tin/i })[1]);
    fireEvent.click(await screen.findByRole("menuitem", { name: /Sao chép|Sao chÃ©p/i }));

    expect(await screen.findByText(/Message action failed:/i)).toBeInTheDocument();
    expect(screen.getByText(/Clipboard denied/i)).toBeInTheDocument();
  });
});
