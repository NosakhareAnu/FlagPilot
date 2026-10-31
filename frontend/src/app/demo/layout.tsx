import type { Metadata } from "next";

export const metadata: Metadata = { title: "Demo app" };

export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return children;
}
