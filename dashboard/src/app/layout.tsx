import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const DESCRIPTION =
  "A read-only record of an autonomous options agent: every cycle, every model's reasoning, " +
  "and every trade the risk gate refused.";

// The tab title and the link preview are the same string, and this page gets shared. The
// default create-next-app metadata was still in place until the day the URL went out, which
// would have unfurled the project as "Create Next App" on every post carrying it.
export const metadata: Metadata = {
  metadataBase: new URL("https://alpaca-trade-intelli.vercel.app"),
  title: "Brightline — agent dashboard",
  description: DESCRIPTION,
  openGraph: {
    title: "Brightline — agent dashboard",
    description: DESCRIPTION,
    type: "website",
    siteName: "Brightline",
  },
  twitter: {
    card: "summary_large_image",
    title: "Brightline — agent dashboard",
    description: DESCRIPTION,
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
