import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PaymentsPage } from "./PaymentsPage";
import { renderDashboard } from "../test/test-utils";

function payment(index: number) {
  const id = String(index).padStart(32, "0");
  return {
    payment_id: `pay_${id}`,
    amount_minor: 2599,
    currency: "USD",
    status: "pending",
    created_at: "2026-10-26T10:00:00Z",
    updated_at: "2026-10-26T10:00:00Z",
  };
}

function page(
  items: ReturnType<typeof payment>[],
  offset: number,
  total: number,
) {
  return new Response(JSON.stringify({ items, total, limit: 10, offset }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Payments page", () => {
  it("loads real pages from the API and navigates using server pagination", async () => {
    let resolveFirst!: (response: Response) => void;
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveFirst = resolve;
          }),
      )
      .mockResolvedValueOnce(page([payment(11)], 10, 11));
    vi.stubGlobal("fetch", fetchMock);
    renderDashboard(<PaymentsPage />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading payments");
    await act(async () => {
      resolveFirst(
        page(
          Array.from({ length: 10 }, (_, index) => payment(index + 1)),
          0,
          11,
        ),
      );
    });

    expect(
      await screen.findByRole("link", {
        name: `View payment ${payment(1).payment_id}`,
      }),
    ).toHaveAttribute("href", `/payments/${payment(1).payment_id}`);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/v1/payments?limit=10&offset=0",
    );
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(
      screen.getByText(/Search and filters are not available/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("11–11 of 11")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      "/api/v1/payments?limit=10&offset=10",
    );
    expect(
      screen.getByRole("link", {
        name: `View payment ${payment(11).payment_id}`,
      }),
    ).toHaveAttribute("href", `/payments/${payment(11).payment_id}`);
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(await screen.findByText("1–10 of 11")).toBeInTheDocument();
  });

  it("shows the API-backed empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([], 0, 0)));
    renderDashboard(<PaymentsPage />);

    expect(await screen.findByText("No payments found")).toBeInTheDocument();
    expect(screen.getByText("0 records")).toBeInTheDocument();
  });

  it("offers retry after a failed request", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(page([], 0, 0));
    vi.stubGlobal("fetch", fetchMock);
    renderDashboard(<PaymentsPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "We couldn’t load this data",
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No payments found")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
