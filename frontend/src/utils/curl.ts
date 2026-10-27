import type { CreatePaymentPayload } from "../api/types";
import { API_BASE_URL } from "../api/client";

function shellQuote(value: string): string {
  return `'${value.replaceAll("'", "''")}'`;
}

export function buildCurlCommand(
  payload: CreatePaymentPayload,
  idempotencyKey: string,
  scope: string,
  apiBaseUrl = API_BASE_URL,
  authUsername: string | null = null,
): string {
  const origin =
    typeof window === "undefined"
      ? "http://127.0.0.1:8000"
      : window.location.origin;
  const apiUrl = new URL(apiBaseUrl || origin, origin);
  apiUrl.username = "";
  apiUrl.password = "";
  apiUrl.pathname = `${apiUrl.pathname.replace(/\/+$/, "")}/`;
  apiUrl.search = "";
  apiUrl.hash = "";
  const endpoint = new URL("api/v1/payments", apiUrl).toString();
  const body = JSON.stringify(payload);
  const authentication = authUsername
    ? [`  --user ${shellQuote(authUsername)} \`]
    : [];
  return [
    `curl.exe -X POST ${shellQuote(endpoint)} \``,
    ...authentication,
    `  -H 'Content-Type: application/json' \``,
    `  -H ${shellQuote(`Idempotency-Key: ${idempotencyKey}`)} \``,
    `  -H ${shellQuote(`Idempotency-Scope: ${scope}`)} \``,
    `  --data-raw ${shellQuote(body)}`,
  ].join("\n");
}
