import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { clearApiCredentials } from "../api/client";
import { renderDashboard } from "../test/test-utils";
import { LoginPage } from "./LoginPage";

function authResponse(status: number) {
  return new Response(
    status === 200
      ? JSON.stringify({ status: "authenticated" })
      : JSON.stringify({
          error: {
            code: "authentication_required",
            message: "Valid credentials are required.",
          },
          request_id: "8c86240c-344f-44af-8bca-0e2c9dd4fa9e",
        }),
    {
      status,
      headers: { "Content-Type": "application/json" },
    },
  );
}

describe("Login page", () => {
  afterEach(() => {
    clearApiCredentials();
  });

  it("verifies credentials through the API and keeps them out of persistent storage", async () => {
    const fetchMock = vi.fn().mockResolvedValue(authResponse(200));
    vi.stubGlobal("fetch", fetchMock);
    const onAuthenticated = vi.fn();
    renderDashboard(<LoginPage onAuthenticated={onAuthenticated} />);

    fireEvent.change(screen.getByLabelText("Username"), {
      target: { value: "portfolio-operator" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "a-long-demo-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledOnce());
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/auth/verify");
    expect(fetchMock.mock.calls[0]?.[1]?.headers).toMatchObject({
      Authorization: `Basic ${btoa("portfolio-operator:a-long-demo-password")}`,
    });
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBeUndefined();
    expect(window.sessionStorage.length).toBe(0);
    expect(window.localStorage.length).toBe(0);
  });

  it("shows a generic message for rejected credentials", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(authResponse(401)));
    renderDashboard(<LoginPage onAuthenticated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Username"), {
      target: { value: "portfolio-operator" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent("The username or password was not accepted.");
  });
});
