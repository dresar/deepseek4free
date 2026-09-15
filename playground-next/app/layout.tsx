import './globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ROBOT-DSK | DeepSeek R1',
  description: 'Futuristic AI Playground',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="id" className="dark">
      <body className="bg-[#070a0f] text-slate-200 antialiased selection:bg-[#00f0ff33] selection:text-[#00f0ff]">
        {children}
      </body>
    </html>
  )
}
