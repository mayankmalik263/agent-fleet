// Our stylesheet comes first: it declares the CSS layer order (React Flow styles sit in @layer xyflow).
import "@/styles/globals.css";
import "@xyflow/react/dist/style.css";
import type { Metadata, Viewport } from "next";
import { Suspense, type ReactNode } from "react";
import { Sidebar } from "@/components/shell/Sidebar";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Agent Fleet",
  description: "Local-first multi-agent orchestration and observability console.",
};

export const viewport: Viewport = {
  themeColor: "#171719",
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-bg text-fg">
        <Providers>
          <div className="flex min-h-screen flex-col md:h-screen md:flex-row md:overflow-hidden">
            <Suspense fallback={<div className="shrink-0 md:w-14 xl:w-48" />}>
              <Sidebar />
            </Suspense>
            <main id="main" className="flex min-w-0 flex-1 flex-col md:overflow-y-auto">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
