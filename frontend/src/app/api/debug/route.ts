import { NextResponse } from "next/server";

export async function GET() {
  try {
    const r = await fetch(
      "http://localhost:8000/api/sales/kpis?date_from=2026-01-18&date_to=2026-04-18",
    );
    const data = await r.json();
    return NextResponse.json({ ok: true, data, status: r.status });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: String(e) });
  }
}
