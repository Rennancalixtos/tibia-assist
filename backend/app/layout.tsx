export const metadata = {
  title: "EasyF",
  description: "Cadastro e assinatura do EasyF",
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
