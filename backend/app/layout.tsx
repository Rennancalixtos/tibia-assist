export const metadata = {
  title: "TibiaAssist",
  description: "Cadastro e assinatura do TibiaAssist",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#111318", color: "#e7e7ea" }}>
        {children}
      </body>
    </html>
  );
}
