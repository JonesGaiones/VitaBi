import numeral from "numeral";

// registrar locale pt-BR (numeral não vem com o locale em runtime do browser
// de forma estável, então fazemos manual)
numeral.register("locale", "pt-br-vita", {
  delimiters: { thousands: ".", decimal: "," },
  abbreviations: { thousand: "k", million: "mi", billion: "bi", trillion: "tri" },
  ordinal: () => "º",
  currency: { symbol: "R$" },
});
numeral.locale("pt-br-vita");

export function fmtCurrency(n: number | null | undefined, compact = false): string {
  if (n === null || n === undefined || isNaN(n)) return "—";
  if (compact && Math.abs(n) >= 1000) {
    return `R$ ${numeral(n).format("0.[0]a")}`;
  }
  return numeral(n).format("$0,0.00");
}

export function fmtNumber(n: number | null | undefined, compact = false): string {
  if (n === null || n === undefined || isNaN(n)) return "—";
  if (compact && Math.abs(n) >= 1000) return numeral(n).format("0.[0]a");
  return numeral(n).format("0,0.[00]");
}

export function fmtPercent(n: number | null | undefined, fractionDigits = 1): string {
  if (n === null || n === undefined || isNaN(n)) return "—";
  const pct = Math.abs(n) < 1 ? n * 100 : n;
  return `${pct.toFixed(fractionDigits)}%`;
}

export function fmtDelta(n: number | null | undefined): { label: string; sign: "up" | "down" | "flat" } {
  if (n === null || n === undefined || isNaN(n)) return { label: "—", sign: "flat" };
  const sign = n > 0.001 ? "up" : n < -0.001 ? "down" : "flat";
  const prefix = sign === "up" ? "+" : "";
  return { label: `${prefix}${n.toFixed(1)}%`, sign };
}
