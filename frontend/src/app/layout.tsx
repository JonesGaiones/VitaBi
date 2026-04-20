import type { Metadata } from "next";
import { Fraunces, JetBrains_Mono } from "next/font/google";
import "@/styles/globals.css";
import { Providers } from "@/components/providers";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  axes: ["opsz", "SOFT"],
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

// Geist é self-hosted via CSS variables. Adicione os arquivos em /public/fonts
// ou troque para "Inter" se quiser CDN.

export const metadata: Metadata = {
  title: "Vita BI — Inteligência de Vendas",
  description: "Dashboard operacional da Vita Forte Inc.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="pt-BR"
      className={`${fraunces.variable} ${mono.variable}`}
      style={{ "--font-sans": "'Geist Sans', system-ui, sans-serif" } as React.CSSProperties}
    >
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
