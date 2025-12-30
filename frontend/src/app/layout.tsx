import type { Metadata } from "next";
import { Inter, Noto_Sans_KR } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import { Footer } from "@/components/ui/Footer";
import CommandPalette from "@/components/ui/CommandPalette";
import { Toolbar } from "@/components/ui/Toolbar";
import { Button } from "@/components/ui/Button";

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
            <main className="flex-1 overflow-y-auto bg-muted/20">
              <div className="sticky top-0 z-20">
                <Toolbar
                  title="Dropshipping ERP"
                  subtitle="운영 현황, 재고, 주문을 한 화면에서 관리하세요."
                  metaItems={[
                    { label: "환경", value: "LOCAL" },
                    { label: "모드", value: "ERP" },
                    { label: "표시", value: "전체" },
                  ]}
                  showSearch
                  showNotification
                  notificationCount={0}
                  actions={
                    <div className="hidden lg:flex items-center gap-2">
                      <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                        빠른 실행
                      </span>
                      <div className="flex items-center gap-1">
                        <Button variant="secondary" size="xs">가공</Button>
                        <Button variant="secondary" size="xs">등록</Button>
                        <Button variant="secondary" size="xs">소싱</Button>
                      </div>
                    </div>
                  }
                  className="bg-card/95 backdrop-blur"
                />
              </div>
              <div className="px-4 py-4">
                <div className="max-w-[1400px] mx-auto space-y-4">
                  {children}
                </div>
              </div>
            </main>
            <Footer />
            <CommandPalette />
          </div>
        </div>
      </body>
    </html>
  );
}
