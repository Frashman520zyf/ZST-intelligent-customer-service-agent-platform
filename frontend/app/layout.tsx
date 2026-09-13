import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "智扫通 | 智能客服与售后工作台",
  description: "面向智能扫地机器人的客服、售后与使用报告平台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
