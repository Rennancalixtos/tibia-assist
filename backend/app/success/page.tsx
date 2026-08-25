"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

type Status = "loading" | "ready" | "timeout" | "error";

const cardStyle: React.CSSProperties = {
  maxWidth: 420,
  margin: "64px auto",
  padding: 24,
  background: "#1a1d24",
  borderRadius: 12,
  border: "1px solid #2a2d36",
  textAlign: "center",
};

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 15000;

export default function SuccessPage() {
  return (
    <Suspense fallback={<div style={cardStyle}>Carregando...</div>}>
      <SuccessContent />
    </Suspense>
  );
}

function SuccessContent() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session_id");
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    if (!sessionId) {
      setStatus("error");
      return;
    }

    let cancelled = false;
    const startedAt = Date.now();

    async function poll() {
      try {
        const res = await fetch(`/api/license/by-session?session_id=${encodeURIComponent(sessionId as string)}`);
        const data = await res.json();

        if (cancelled) return;

        if (res.status === 200 && data.ready) {
          setStatus("ready");
          return;
        }

        if (Date.now() - startedAt >= POLL_TIMEOUT_MS) {
          setStatus("timeout");
          return;
        }

        setTimeout(poll, POLL_INTERVAL_MS);
      } catch {
        if (cancelled) return;
        if (Date.now() - startedAt >= POLL_TIMEOUT_MS) {
          setStatus("timeout");
          return;
        }
        setTimeout(poll, POLL_INTERVAL_MS);
      }
    }

    poll();

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  return (
    <div style={cardStyle}>
      {status === "loading" && (
        <>
          <h1 style={{ fontSize: 18 }}>Confirmando seu pagamento...</h1>
          <p style={{ color: "#8a8f9c", fontSize: 14 }}>Isso pode levar alguns segundos.</p>
        </>
      )}

      {status === "ready" && (
        <>
          <h1 style={{ fontSize: 18, color: "#6bffa0" }}>Assinatura ativa!</h1>
          <p style={{ color: "#e7e7ea", fontSize: 14 }}>
            Volte para o EasyF e faca login com o email e senha que voce
            cadastrou.
          </p>
        </>
      )}

      {(status === "timeout" || status === "error") && (
        <>
          <h1 style={{ fontSize: 18, color: "#ff6b6b" }}>Ainda confirmando...</h1>
          <p style={{ color: "#8a8f9c", fontSize: 14 }}>
            Nao conseguimos confirmar sua assinatura ainda. Atualize esta
            pagina em alguns instantes ou volte para o EasyF e tente
            fazer login - a assinatura pode ja estar ativa.
          </p>
        </>
      )}
    </div>
  );
}
