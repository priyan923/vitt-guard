import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { clearApiCredentials, getAuthStatus } from "./api/client";
import { AppShell } from "./components/AppShell";
import { ApiExplorerPage } from "./pages/ApiExplorerPage";
import { OverviewPage } from "./pages/OverviewPage";
import { LoginPage } from "./pages/LoginPage";
import { PaymentDetailPage } from "./pages/PaymentDetailPage";
import { PaymentsPage } from "./pages/PaymentsPage";
import { RequestDetailPage } from "./pages/RequestDetailPage";
import { RequestsPage } from "./pages/RequestsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 15_000,
      refetchOnWindowFocus: false,
    },
  },
});

function NotFoundPage() {
  return (
    <section className="panel not-found">
      <p className="eyebrow">404 · PAGE NOT FOUND</p>
      <h1>This page doesn’t exist.</h1>
      <p>
        Use the workspace navigation to return to a supported dashboard page.
      </p>
    </section>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Application />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

function Application() {
  const queryClient = useQueryClient();
  const [authenticated, setAuthenticated] = useState(false);
  const authStatus = useQuery({
    queryKey: ["auth-status"],
    queryFn: async () => (await getAuthStatus()).data,
  });

  if (authStatus.isPending) {
    return (
      <main className="auth-page" aria-live="polite">
        Connecting to Vitt Guard…
      </main>
    );
  }
  if (authStatus.isError) {
    return (
      <main className="auth-page">
        <section className="panel auth-panel" role="alert">
          <h1>Vitt Guard is unavailable</h1>
          <p>Authentication settings could not be loaded from the API.</p>
          <button
            className="button button--primary"
            onClick={() => void authStatus.refetch()}
            type="button"
          >
            Retry
          </button>
        </section>
      </main>
    );
  }

  const logout = authStatus.data.authentication_required
    ? () => {
        clearApiCredentials();
        queryClient.clear();
        setAuthenticated(false);
      }
    : undefined;

  if (authStatus.data.authentication_required && !authenticated) {
    return <LoginPage onAuthenticated={() => setAuthenticated(true)} />;
  }

  return (
    <Routes>
      <Route element={<AppShell onLogout={logout} />}>
        <Route index element={<OverviewPage />} />
        <Route path="payments" element={<PaymentsPage />} />
        <Route path="payments/:paymentId" element={<PaymentDetailPage />} />
        <Route path="requests" element={<RequestsPage />} />
        <Route path="requests/:requestId" element={<RequestDetailPage />} />
        <Route path="explorer" element={<ApiExplorerPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
