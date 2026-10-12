import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Shorts Maker",
  description: "Автоматический поиск лучших моментов YouTube-видео",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}