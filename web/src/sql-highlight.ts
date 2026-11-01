// Minimal, dependency-free SQL/PL-pgSQL highlighter.
// Escapes HTML first, then wraps comments, strings, and keywords in spans.

const KEYWORDS = [
  "select", "insert", "update", "delete", "merge", "truncate", "from", "where", "join",
  "left", "right", "inner", "outer", "full", "on", "using", "group", "order", "by", "having",
  "limit", "offset", "into", "values", "set", "returning", "with", "as", "and", "or", "not",
  "null", "is", "in", "exists", "case", "when", "then", "else", "end", "create", "replace",
  "function", "procedure", "returns", "language", "begin", "declare", "if", "elsif", "loop",
  "while", "for", "return", "query", "execute", "format", "distinct", "union", "all", "count",
  "sum", "avg", "min", "max", "coalesce", "default", "trigger", "new", "old",
];

const KEYWORD_RE = new RegExp(`\\b(${KEYWORDS.join("|")})\\b`, "gi");

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function highlightSql(sql: string): string {
  // Split out string literals and comments so keywords inside them are not highlighted.
  const tokens: { text: string; kind: "code" | "string" | "comment" }[] = [];
  const re = /('(?:[^']|'')*')|(--[^\n]*)|(\/\*[\s\S]*?\*\/)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(sql)) !== null) {
    if (m.index > last) tokens.push({ text: sql.slice(last, m.index), kind: "code" });
    if (m[1]) tokens.push({ text: m[1], kind: "string" });
    else if (m[2]) tokens.push({ text: m[2], kind: "comment" });
    else if (m[3]) tokens.push({ text: m[3], kind: "comment" });
    last = re.lastIndex;
  }
  if (last < sql.length) tokens.push({ text: sql.slice(last), kind: "code" });

  return tokens
    .map((t) => {
      const safe = escapeHtml(t.text);
      if (t.kind === "string") return `<span class="tok-string">${safe}</span>`;
      if (t.kind === "comment") return `<span class="tok-comment">${safe}</span>`;
      return safe.replace(KEYWORD_RE, (kw) => `<span class="tok-kw">${kw}</span>`);
    })
    .join("");
}
