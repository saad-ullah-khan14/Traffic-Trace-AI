import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Shell } from "@/components/Shell";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Traffic_Trace",
  description: "Tracking vehicles that have no readable number plate",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* Sidebar hides itself below sm:, so the phone camera page stays full-width. */}
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
