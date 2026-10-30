import type { Metadata, Viewport } from "next";
import { Suspense } from "react";
import { Footer } from "@/components/Footer";
import { Header, HeaderShell } from "@/components/Header";
import { ModeBanners, ModeProvider } from "@/components/mode";
import { SITE } from "@/lib/site";
import "./globals.css";

const TITLE = "Safe Cut: publish street footage without exposing bystanders";
const DESCRIPTION =
  "Safe Cut works out who's part of your story and hides everyone and everything else: passers-by, children, number plates, private screens. You approve every decision.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE.siteUrl),
  title: TITLE,
  description: DESCRIPTION,
  openGraph: { title: TITLE, description: DESCRIPTION, type: "website", images: [{ url: "/sample/safe-cut.jpg", width: 1280, height: 720, alt: "A street scene with the guest clear and a passer-by, a child, a number plate and a private screen covered" }] },
  twitter: { card: "summary_large_image", title: TITLE, description: DESCRIPTION, images: ["/sample/safe-cut.jpg"] },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f6f3" },
    { media: "(prefers-color-scheme: dark)", color: "#121211" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full">
      <body className="flex min-h-full flex-col">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
          Skip to content
        </a>
        <ModeProvider>
          <Suspense fallback={<HeaderShell />}>
            <Header />
          </Suspense>
          <ModeBanners />
          <main id="main" className="flex-1">
            {children}
          </main>
          <Footer />
        </ModeProvider>
      </body>
    </html>
  );
}
