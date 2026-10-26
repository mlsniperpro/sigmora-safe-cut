import type { Metadata } from "next";
import { MessagePage } from "@/components/ui";
import { SITE } from "@/lib/site";

export const metadata: Metadata = { title: "Not available in your region · Safe Cut", robots: { index: false } };

export default function Unavailable() {
  return (
    <MessagePage
      message="Safe Cut isn't available in your region, because Meta's Model API, which it runs on, isn't offered there. You can still watch the demo."
      actions={[
        { label: "Watch the demo", href: "/" },
        { label: "Meta's Geographic Use Policy ↗", href: SITE.geoPolicyUrl },
      ]}
    />
  );
}
