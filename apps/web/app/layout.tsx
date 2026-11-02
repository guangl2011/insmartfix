import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import '@insmartfix/tokens/tokens.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'InsmartFix',
  description: 'Insmart AI field app for contractors',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#F4F6F8' },
    { media: '(prefers-color-scheme: dark)', color: '#0D1417' },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
