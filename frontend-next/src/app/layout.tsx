import type { Metadata } from "next";
import { Bitter, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const bitter = Bitter({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-heading",
  display: "swap",
});

const ibmPlexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-body",
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "GCLBA Compliance Tracker",
  description: "Desk research triage tool for Genesee County Land Bank Authority compliance inspections",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${bitter.variable} ${ibmPlexSans.variable} ${ibmPlexMono.variable}`}>
      <body className="bg-warm-50 font-body text-gray-900 antialiased">
        {children}
      </body>
    </html>
  );
}
