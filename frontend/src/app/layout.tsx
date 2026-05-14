import type { Metadata } from "next";
import { JetBrains_Mono, Noto_Sans_SC } from "next/font/google";

import "./globals.css";

const notoSansSC = Noto_Sans_SC({
  variable: "--font-sans",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "\u6c42\u804c\u9762\u8bd5 Agent",
  description:
    "\u4e00\u4e2a\u7528\u4e8e\u6c42\u804c\u95ee\u7b54\u3001\u5c97\u4f4d\u5206\u6790\u548c\u9762\u8bd5\u51c6\u5907\u7684 Agent\u3002",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className={`${notoSansSC.variable} ${jetbrainsMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
