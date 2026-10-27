import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Payment, RequestLog } from "../api/types";
import { ApiExplorerPage } from "./ApiExplorerPage";
import { RequestDetailPage } from "./RequestDetailPage";
import { renderDashboard } from "../test/test-utils";
import { buildCurlCommand } from "../utils/curl";
import { Route, Routes } from "react-router-dom";

const payment: Payment = {
  payment_id: "pay_0123456789abcdef0123456789abcdef",
  amount_minor: 2499,
  currency: "USD",
  status: "pending",
  created_at: "2026-10-26T10:00:00Z",
  updated_at: "2026-10-26T10:00:00Z",
};

const requestIds = {
  created: "8c86240c-344f-44af-8bca-0e2c9dd4fa9e",
  replayed: "f4619fd3-9b2c-4a64-9c78-c6cc8cfe47bb",
  conflict: "142ea459-5355-4d1a-b46a-6e9e76a7d6b5",
  validation: "a478acde-0a26-47b2-8fe8-1f132ca5cb18",
};
let originalClipboardDescriptor: PropertyDescriptor | undefined;

function response(body: unknown, status: number, requestId: string) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": requestId,
    },
  });
}

function requestLog(
  requestId: string,
  outcome: string,
  idempotencyOutcome: string,
  status: number,
): RequestLog {
  return {
    request_id: requestId,
    request_method: "POST",
    api_path: "/api/v1/payments",
    request_at: "2026-10-26T10:00:00Z",
    http_status_code: status,
    processing_duration_ms: 4,
    idempotency_outcome: idempotencyOutcome,
    outcome,
    payment_id: payment.payment_id,
    sanitized_error_code: status >= 400 ? "idempotency_key_reused" : null,
  };
}

function renderExplorerFlow() {
  return renderDashboard(
    <Routes>
      <Route path="/explorer" element={<ApiExplorerPage />} />
      <Route path="/requests/:requestId" element={<RequestDetailPage />} />
    </Routes>,
    ["/explorer"],
  );
}

describe("API Explorer", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    originalClipboardDescriptor = Object.getOwnPropertyDescriptor(
      navigator,
      "clipboard",
    );
  });

  afterEach(() => {
    if (originalClipboardDescriptor) {
      Object.defineProperty(
        navigator,
        "clipboard",
        originalClipboardDescriptor,
      );
    } else {
      Reflect.deleteProperty(navigator, "clipboard");
    }
  });

  it("creates, explicitly replays, conflicts, and inspects actual request records", async () => {
    const fetchMock = vi.mocked(fetch);
    const logs = new Map<string, RequestLog>([
      [
        requestIds.created,
        requestLog(requestIds.created, "payment_created", "created", 201),
      ],
      [
        requestIds.replayed,
        requestLog(requestIds.replayed, "idempotency_replay", "replayed", 200),
      ],
      [
        requestIds.conflict,
        requestLog(
          requestIds.conflict,
          "payload_conflict",
          "payload_mismatch",
          409,
        ),
      ],
    ]);
    let paymentCalls = 0;
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/api/v1/payments" && init?.method === "POST") {
        paymentCalls += 1;
        if (paymentCalls === 1) {
          return response(payment, 201, requestIds.created);
        }
        if (paymentCalls === 2) {
          return response(payment, 200, requestIds.replayed);
        }
        return response(
          {
            error: {
              code: "idempotency_key_reused",
              message:
                "This idempotency key was already used with a different request.",
            },
            request_id: requestIds.conflict,
          },
          409,
          requestIds.conflict,
        );
      }
      const requestId = url.split("/").at(-1) ?? "";
      const log = logs.get(requestId);
      if (log)
        return response(log, 200, "d18f1045-17cb-4e48-b3ed-a5375473b9cf");
      throw new Error(`Unexpected test-backend request: ${url}`);
    });

    renderExplorerFlow();
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));
    expect(
      await screen.findByText("New payment created (HTTP 201)."),
    ).toBeVisible();
    expect(await screen.findByText("created", { exact: true })).toBeVisible();

    const key = (screen.getByLabelText("Idempotency key") as HTMLInputElement)
      .value;
    const firstCall = fetchMock.mock.calls[0]!;
    const firstInit = firstCall[1];

    fireEvent.click(
      screen.getByRole("button", { name: "Retry exact request" }),
    );
    expect(
      await screen.findByText(/Replay confirmed by the API \(HTTP 200\)/),
    ).toBeVisible();
    expect(await screen.findByText("replayed", { exact: true })).toBeVisible();
    const replayCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url) === "/api/v1/payments" &&
        init?.method === "POST" &&
        init.body === firstInit?.body,
    );
    expect(replayCall).toBeDefined();
    expect(replayCall?.[1]?.headers).toMatchObject({
      "Idempotency-Key": key,
      "Idempotency-Scope": "default",
    });
    expect(replayCall?.[1]?.body).toBe(firstInit?.body);

    fireEvent.change(screen.getByLabelText("Amount in minor units"), {
      target: { value: "2500" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));
    expect(await screen.findByText("409")).toBeVisible();
    expect(
      await screen.findByText(
        "This idempotency key was already used with a different request.",
      ),
    ).toBeVisible();
    expect(await screen.findByText("payload mismatch")).toBeVisible();
    const paymentLink = screen.getByRole("link", {
      name: /pay_0123456789abcdef01/,
    });
    expect(paymentLink).toHaveAttribute(
      "href",
      `/payments/${payment.payment_id}`,
    );
    const paymentRequests = fetchMock.mock.calls.filter(
      ([url, init]) =>
        String(url) === "/api/v1/payments" && init?.method === "POST",
    );
    expect(paymentRequests).toHaveLength(3);
    expect(paymentRequests[2]?.[1]?.headers).toMatchObject({
      "Idempotency-Key": key,
    });
    expect(JSON.parse(String(paymentRequests[2]?.[1]?.body))).toEqual({
      amount_minor: 2500,
      currency: "USD",
    });

    fireEvent.click(screen.getByRole("link", { name: "Inspect request" }));
    expect(
      await screen.findByRole("heading", { name: "Request attempt" }),
    ).toBeVisible();
    expect(
      (await screen.findAllByText("payload conflict")).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("link", { name: /pay_0123456789abcdef/ }),
    ).toHaveAttribute("href", `/payments/${payment.payment_id}`);
  });

  it("shows server validation errors as rejected requests, not unknown outcomes", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async (input) => {
      if (String(input) === "/api/v1/payments") {
        return response(
          {
            error: { code: "validation_error", message: "Invalid amount." },
            request_id: requestIds.validation,
          },
          422,
          requestIds.validation,
        );
      }
      return response(
        requestLog(requestIds.validation, "validation_error", "not_used", 422),
        200,
        "d18f1045-17cb-4e48-b3ed-a5375473b9cf",
      );
    });
    renderDashboard(<ApiExplorerPage />);

    fireEvent.click(screen.getByRole("button", { name: "Send request" }));

    expect(await screen.findByText("422")).toBeVisible();
    expect(
      await screen.findByText(/Validation rejected by the API \(HTTP 422\)/),
    ).toBeVisible();
    expect(
      screen.queryByText(/operation result is unknown/i),
    ).not.toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
  });

  it("blocks invalid form input before sending any request", () => {
    const fetchMock = vi.mocked(fetch);
    renderDashboard(<ApiExplorerPage />);
    fireEvent.change(screen.getByLabelText("Amount in minor units"), {
      target: { value: "0" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Amount in minor units")).toBeInvalid();
  });

  it("shows unexpected server failures without a success-shaped result", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async (input) => {
      if (String(input) === "/api/v1/payments") {
        return response(
          {
            error: {
              code: "internal_error",
              message: "The request could not be completed.",
            },
            request_id: requestIds.validation,
          },
          500,
          requestIds.validation,
        );
      }
      return response(
        {
          ...requestLog(
            requestIds.validation,
            "handled_error",
            "not_used",
            500,
          ),
          sanitized_error_code: "internal_error",
          payment_id: null,
        },
        200,
        "d18f1045-17cb-4e48-b3ed-a5375473b9cf",
      );
    });
    renderDashboard(<ApiExplorerPage />);

    fireEvent.click(screen.getByRole("button", { name: "Send request" }));

    expect(await screen.findByText("500")).toBeVisible();
    expect(await screen.findByText("The API returned HTTP 500.")).toBeVisible();
    expect(screen.queryByText(/New payment created/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Replay confirmed/)).not.toBeInTheDocument();
  });

  it("treats an unavailable backend as an unknown outcome and retries only the exact request", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderDashboard(<ApiExplorerPage />);

    const keyInput = screen.getByLabelText("Idempotency key");
    const originalKey = (keyInput as HTMLInputElement).value;
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));

    expect(await screen.findByText(/network connection failed/i)).toBeVisible();
    expect(screen.getByText("No HTTP response")).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "Retry exact request" }),
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    expect((keyInput as HTMLInputElement).value).toBe(originalKey);
    expect(fetchMock.mock.calls[0]?.[1]?.headers).toMatchObject({
      "Idempotency-Key": originalKey,
    });
    expect(fetchMock.mock.calls[1]?.[1]?.headers).toMatchObject({
      "Idempotency-Key": originalKey,
    });
    expect(fetchMock.mock.calls[1]?.[1]?.body).toBe(
      fetchMock.mock.calls[0]?.[1]?.body,
    );
    expect(screen.queryByText(/New payment created/)).not.toBeInTheDocument();
  });

  it("reports request timeouts as unknown and keeps retry available", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_input: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => {
              reject(
                new DOMException("The operation was aborted.", "AbortError"),
              );
            });
          }),
      ),
    );
    renderDashboard(<ApiExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });

    expect(
      screen.getAllByText(/The request timed out/i).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: "Retry exact request" }),
    ).toBeEnabled();
    vi.useRealTimers();
  });

  it("copies a PowerShell cURL command generated from the selected form values", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    renderDashboard(<ApiExplorerPage />);
    fireEvent.change(screen.getByLabelText("Amount in minor units"), {
      target: { value: "734" },
    });
    fireEvent.change(screen.getByLabelText("Currency"), {
      target: { value: "EUR" },
    });
    fireEvent.change(screen.getByLabelText("Idempotency key"), {
      target: { value: "selected-key-01" },
    });
    fireEvent.change(screen.getByLabelText("Idempotency scope"), {
      target: { value: "local.test" },
    });
    const commandElement = screen.getByText(
      (_, element) =>
        element?.tagName === "CODE" &&
        Boolean(element.textContent?.includes("selected-key-01")),
    );
    const command = commandElement.textContent ?? "";

    fireEvent.click(screen.getByRole("button", { name: "Copy cURL command" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(command));
    expect(command).toContain("curl.exe -X POST");
    expect(command).toContain('"amount_minor":734');
    expect(command).toContain('"currency":"EUR"');
    expect(command).toContain("Idempotency-Scope: local.test");
    expect(
      screen.getByRole("button", { name: "Copied to clipboard" }),
    ).toBeInTheDocument();
  });

  it("generates a cURL command with the configured origin and escaped values, without URL credentials", () => {
    const command = buildCurlCommand(
      { amount_minor: 734, currency: "EUR" },
      "key'with-quote",
      "scope'with-quote",
      "https://user:secret@api.example.test/v2?token=private#fragment",
    );
    expect(command).toContain("curl.exe -X POST");
    expect(command).toContain("https://api.example.test/v2/api/v1/payments");
    expect(command).not.toContain("secret");
    expect(command).not.toContain("private");
    expect(command).toContain(`Idempotency-Key: key''with-quote`);
    expect(command).toContain(`Idempotency-Scope: scope''with-quote`);
    expect(command).toContain('"amount_minor":734');
    expect(command).toContain('"currency":"EUR"');
  });

  it("adds the authenticated username to cURL without embedding a password", () => {
    const command = buildCurlCommand(
      { amount_minor: 734, currency: "EUR" },
      "safe-key",
      "default",
      "https://api.example.test",
      "portfolio-operator",
    );

    expect(command).toContain("--user 'portfolio-operator'");
    expect(command).not.toContain("password");
  });
});
