import type { Metadata } from "next";
import { ProvidersView } from "@/features/providers/ProvidersView";

export const metadata: Metadata = { title: "Providers · Agent Fleet" };

export default function Page() {
  return <ProvidersView />;
}
