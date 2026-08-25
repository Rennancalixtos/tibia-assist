"use client";

import { useState } from "react";

type Tab = "cadastrar" | "entrar";

const cardStyle: React.CSSProperties = {
  maxWidth: 420,
  margin: "64px auto",
  padding: 24,
  background: "#1a1d24",
  borderRadius: 12,
  border: "1px solid #2a2d36",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  marginBottom: 12,
  borderRadius: 8,
  border: "1px solid #363a45",
  background: "#0f1115",
  color: "#e7e7ea",
  boxSizing: "border-box",
};

const buttonStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: 8,
  border: "none",
  background: "#4f7cff",
  color: "#fff",
  fontWeight: 600,
  cursor: "pointer",
};

const tabButtonStyle = (active: boolean): React.CSSProperties => ({
  flex: 1,
  padding: "10px 0",
  textAlign: "center",
  cursor: "pointer",
  background: active ? "#1a1d24" : "transparent",
  color: active ? "#e7e7ea" : "#8a8f9c",
  border: "none",
  borderBottom: active ? "2px solid #4f7cff" : "2px solid #2a2d36",
  fontWeight: 600,
});

export default function HomePage() {
  const [tab, setTab] = useState<Tab>("cadastrar");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [isError, setIsError] = useState(false);

  async function handleCadastrar(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setMessage(null);
    setIsError(false);

    try {
      const signupRes = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const signupData = await signupRes.json();

      if (!signupRes.ok) {
        setIsError(true);
        setMessage(signupData.error ?? "Erro ao cadastrar.");
        setLoading(false);
        return;
      }

      const checkoutRes = await fetch("/api/stripe/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_token: signupData.access_token }),
      });
      const checkoutData = await checkoutRes.json();

      if (!checkoutRes.ok || !checkoutData.url) {
        setIsError(true);
        setMessage(checkoutData.error ?? "Erro ao iniciar pagamento.");
        setLoading(false);
        return;
      }

      window.location.href = checkoutData.url;
    } catch {
      setIsError(true);
      setMessage("Erro de conexao. Tente novamente.");
      setLoading(false);
    }
  }

  async function handleEntrar(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setMessage(null);
    setIsError(false);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();

      if (!res.ok) {
        setIsError(true);
        setMessage(data.error ?? "Erro ao entrar.");
        setLoading(false);
        return;
      }

      setIsError(false);
      setMessage(`Login bem-sucedido. Assinatura: ${data.license.status}`);
      setLoading(false);
    } catch {
      setIsError(true);
      setMessage("Erro de conexao. Tente novamente.");
      setLoading(false);
    }
  }

  return (
    <div style={cardStyle}>
      <h1 style={{ fontSize: 20, marginTop: 0, marginBottom: 16 }}>EasyF</h1>

      <div style={{ display: "flex", marginBottom: 20 }}>
        <button style={tabButtonStyle(tab === "cadastrar")} onClick={() => { setTab("cadastrar"); setMessage(null); }}>
          Cadastrar
        </button>
        <button style={tabButtonStyle(tab === "entrar")} onClick={() => { setTab("entrar"); setMessage(null); }}>
          Entrar
        </button>
      </div>

      {tab === "cadastrar" ? (
        <form onSubmit={handleCadastrar}>
          <p style={{ color: "#8a8f9c", fontSize: 14, marginTop: 0 }}>
            Crie sua conta e assine o EasyF. Depois de assinar, use este
            mesmo email e senha para entrar no aplicativo.
          </p>
          <input
            style={inputStyle}
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            style={inputStyle}
            type="password"
            placeholder="Senha (minimo 6 caracteres)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
          />
          <button style={buttonStyle} type="submit" disabled={loading}>
            {loading ? "Aguarde..." : "Cadastrar e assinar"}
          </button>
        </form>
      ) : (
        <form onSubmit={handleEntrar}>
          <p style={{ color: "#8a8f9c", fontSize: 14, marginTop: 0 }}>
            Use esta aba apenas para verificar sua conta/assinatura. O login
            real e feito dentro do aplicativo EasyF.
          </p>
          <input
            style={inputStyle}
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            style={inputStyle}
            type="password"
            placeholder="Senha"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button style={buttonStyle} type="submit" disabled={loading}>
            {loading ? "Aguarde..." : "Entrar"}
          </button>
        </form>
      )}

      {message && (
        <p style={{ marginTop: 16, color: isError ? "#ff6b6b" : "#6bffa0", fontSize: 14 }}>
          {message}
        </p>
      )}
    </div>
  );
}
