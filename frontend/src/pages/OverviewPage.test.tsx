import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OverviewPage } from "./OverviewPage";
import { renderDashboard } from "../test/test-utils";

describe("Overview page", () => {
  it("shows honest zero-state metrics returned by the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            period_start: null,
            period_end: null,
            total_payments: 0,
            payments_by_status: { pending: 0, succeeded: 0, failed: 0 },
            total_requests: 0,
            payment_attempts: 0,
            successful_requests: 0,
            conflicts: 0,
            idempotency_replays: 0,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    renderDashboard(<OverviewPage />);

    expect(await screen.findByText("No payments yet")).toBeInTheDocument();
    expect(
      screen.getByText("Time-series data isn’t available yet"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("0").length).toBeGreaterThan(0);
  });

  it("offers retry when the metrics request fails", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            period_start: null,
            period_end: null,
            total_payments: 0,
            payments_by_status: { pending: 0, succeeded: 0, failed: 0 },
            total_requests: 0,
            payment_attempts: 0,
            successful_requests: 0,
            conflicts: 0,
            idempotency_replays: 0,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    renderDashboard(<OverviewPage />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          period_start: null,
          period_end: null,
          total_payments: 0,
          payments_by_status: { pending: 0, succeeded: 0, failed: 0 },
          total_requests: 0,
          payment_attempts: 0,
          successful_requests: 0,
          conflicts: 0,
          idempotency_replays: 0,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    screen.getByRole("button", { name: /retry/i }).click();
    expect(await screen.findByText("No payments yet")).toBeInTheDocument();
  });
});
