"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { Toaster } from "sonner";
import { useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60_000,            // 1min → evita refetch desnecessário
        refetchOnWindowFocus: false,
        retry: 1,
      },
    },
  }));

  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster
        theme="dark"
        richColors
        position="bottom-right"
        toastOptions={{
          style: {
            background: "rgba(18, 18, 26, 0.92)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
          },
        }}
      />
      {process.env.NODE_ENV === "development" && <ReactQueryDevtools />}
    </QueryClientProvider>
  );
}
