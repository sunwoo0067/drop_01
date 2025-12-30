import type { Metadata } from "next";
import { Inter, Noto_Sans_KR } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import { Footer } from "@/components/ui/Footer";
import CommandPalette from "@/components/ui/CommandPalette";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const notoSansKr = Noto_Sans_KR({
  variable: "--font-noto-sans-kr",
  subsets: ["latin"],
  weight: ["100", "300", "400", "500", "700", "900"],
});

export const metadata: Metadata = {
  title: "Dropshipping Automation ERP",
  description: "Automated dropshipping management system",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body
        className={`${inter.variable} ${notoSansKr.variable} font-sans antialiased`}
        style={{ fontFamily: 'var(--font-noto-sans-kr), var(--font-inter), sans-serif' }}
      >
        <div className="flex h-screen overflow-hidden bg-background">
          <Sidebar />
          <div className="flex-1 flex flex-col overflow-hidden relative">
            <main className="flex-1 overflow-y-auto">
              {children}
            </main>
            <Footer />
            <CommandPalette />
          </div>
        </div>
      </body>
    </html>
  );
}
