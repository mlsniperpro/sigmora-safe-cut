import type { Metadata } from "next";
import { TryFlow } from "@/components/try/TryFlow";

export const metadata: Metadata = { title: "Try Safe Cut on your own clip" };

export default function TryPage() {
  return <TryFlow />;
}
