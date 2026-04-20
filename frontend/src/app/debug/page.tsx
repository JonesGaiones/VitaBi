"use client";
import { useEffect, useState } from "react";

export default function DebugPage() {
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("http://127.0.0.1:8000/api/sales/kpis?date_from=2026-01-18&date_to=2026-04-18", {
      credentials: "include",
      headers: { Accept: "application/json" },
    })
      .then((r) => r.json())
      .then(setResult)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div style={{ padding: 40, fontFamily: "monospace", background: "#fff", color: "#000" }}>
      <h1>Debug - Teste de conectividade</h1>
      {!result && !error && <p>Carregando...</p>}
      {error && <p style={{ color: "red" }}>ERRO: {error}</p>}
      {result && (
        <div>
          <p style={{ color: "green" }}>✓ API respondeu!</p>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
