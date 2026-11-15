import { createRemoteJWKSet, jwtVerify } from "npm:jose@6.1.0";

const local = Deno.env.get("NEXO_TEST_MODE") === "local";
const project = local ? "http://127.0.0.1:54321" : (Deno.env.get("SUPABASE_URL") || "https://tznebgdgdqpbhjdrhprb.supabase.co").replace(/\/$/, "");
if (!local && !/^https:\/\/[^/?#@]+$/.test(project)) throw new Error("SUPABASE_URL deve ser HTTPS e sem caminho.");
const issuer = project + "/auth/v1";
const resource = project + "/functions/v1/nexo-mcp-test";
const metadata = resource + "/.well-known/oauth-protected-resource";
const internal = local ? "http://kong:8000" : project;
const keys = createRemoteJWKSet(new URL(internal + "/auth/v1/.well-known/jwks.json"));
const publicKey = Deno.env.get("SUPABASE_ANON_KEY") || "";
const clients = new Set((Deno.env.get("NEXO_OAUTH_CLIENT_IDS") || (local ? "" : "451c10f2-5062-45a7-b4df-94664ecf212c")).split(",").map(x => x.trim()).filter(Boolean));
const schemes = [{ type: "oauth2", scopes: ["openid"] }];
const connectionTool = {
  name: "testar_conexao", description: "Testa a conexão autorizada com o NEXO. Não consulta nem altera dados financeiros.",
  inputSchema: { type: "object", properties: {}, additionalProperties: false },
  annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  securitySchemes: schemes, _meta: { securitySchemes: schemes },
};
const entryTool = {
  name: "registrar_lancamento", title: "Registrar receita ou despesa no NEXO",
  description: "Registra uma receita ou despesa exclusivamente na conta NEXO conectada. Funciona também com mensagens ditadas/transcritas. Use apenas valores informados pelo usuário; pergunte quando houver ambiguidade. Converta reais em centavos: R$ 32,50 = 3250. Gere um UUID para cada lançamento e REUTILIZE o mesmo UUID e argumentos ao repetir uma tentativa sem confirmação, evitando duplicatas. Não peça identificador de usuário. Se a data for omitida, usa hoje em America/Sao_Paulo.",
  inputSchema: {
    type: "object", additionalProperties: false,
    required: ["id", "tipo", "valor_centavos", "categoria"],
    properties: {
      id: { type: "string", format: "uuid", description: "UUID estável desta operação; reutilizar ao tentar novamente." },
      tipo: { type: "string", enum: ["receita", "despesa"] },
      valor_centavos: { type: "integer", minimum: 1, maximum: 10000000000 },
      categoria: { type: "string", minLength: 1, maxLength: 120 },
      descricao: { type: "string", maxLength: 200 },
      data: { type: "string", format: "date", description: "Data YYYY-MM-DD; omitida significa hoje em São Paulo." },
    },
  },
  annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  securitySchemes: schemes, _meta: { securitySchemes: schemes },
};
function json(value: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...headers } });
}
function challenge() {
  return json({ error: "unauthorized" }, 401, { "WWW-Authenticate": `Bearer resource_metadata="${metadata}", scope="openid"` });
}
function argumentsForEntry(raw: unknown) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw Error("Informe os dados do lançamento.");
  const a = raw as Record<string, unknown>;
  if (Object.keys(a).some(k => !["id", "tipo", "valor_centavos", "categoria", "descricao", "data"].includes(k))) throw Error("Argumento não permitido.");
  if (typeof a.id !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(a.id)) throw Error("Identificador inválido.");
  if (a.tipo !== "receita" && a.tipo !== "despesa") throw Error("Escolha receita ou despesa.");
  if (typeof a.valor_centavos !== "number" || !Number.isSafeInteger(a.valor_centavos) || a.valor_centavos <= 0 || a.valor_centavos > 10000000000) throw Error("Valor inválido; informe centavos inteiros positivos.");
  if (typeof a.categoria !== "string" || !a.categoria.trim() || a.categoria.length > 120) throw Error("Categoria inválida.");
  if (a.descricao !== undefined && (typeof a.descricao !== "string" || a.descricao.length > 200)) throw Error("Descrição inválida.");
  const date = a.data ?? new Date().toLocaleDateString("sv-SE", { timeZone: "America/Sao_Paulo" });
  if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(Date.parse(date)) || new Date(date).toISOString().slice(0, 10) !== date) throw Error("Data inválida.");
  return { p_id: a.id.toLowerCase(), p_tipo: a.tipo, p_centavos: a.valor_centavos, p_categoria: a.categoria.trim(), p_descricao: typeof a.descricao === "string" ? a.descricao.trim() : "", p_data: date };
}
Deno.serve(async req => {
  const url = new URL(req.url);
  if (req.method === "GET" && url.pathname.endsWith("/.well-known/oauth-protected-resource")) return json({ resource, authorization_servers: [issuer], scopes_supported: ["openid"], bearer_methods_supported: ["header"] });
  if (req.method !== "POST") return new Response(null, { status: 405, headers: { Allow: "POST" } });
  const authorization = req.headers.get("Authorization");
  if (!authorization?.startsWith("Bearer ")) return challenge();
  try {
    const { payload } = await jwtVerify(authorization.slice(7), keys, { issuer, audience: "authenticated", algorithms: ["ES256", "RS256"], requiredClaims: ["exp", "sub", "iss", "aud"] });
    if (payload.role !== "authenticated" || typeof payload.client_id !== "string" || !clients.has(payload.client_id) || typeof payload.sub !== "string") return challenge();
  } catch { return challenge(); }
  let m;
  try { m = await req.json(); } catch { return json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }, 400); }
  if (!m || m.jsonrpc !== "2.0" || typeof m.method !== "string") return json({ jsonrpc: "2.0", id: null, error: { code: -32600, message: "Invalid request" } }, 400);
  if (!Object.prototype.hasOwnProperty.call(m, "id")) return new Response(null, { status: 202 });
  const result = (value: unknown) => json({ jsonrpc: "2.0", id: m.id, result: value });
  const error = (code: number, message: string) => json({ jsonrpc: "2.0", id: m.id, error: { code, message } });
  if (m.method === "initialize") {
    const supported = ["2025-11-25", "2025-06-18", "2025-03-26"];
    return result({ protocolVersion: supported.includes(m.params?.protocolVersion) ? m.params.protocolVersion : "2025-06-18", capabilities: { tools: {} }, serverInfo: { name: "nexo-mcp-test", version: "0.2.0" } });
  }
  if (m.method === "ping") return result({});
  if (m.method === "tools/list") return result({ tools: [connectionTool, entryTool] });
  if (m.method === "tools/call" && m.params?.name === "testar_conexao") return result({ content: [{ type: "text", text: "Conexão OAuth autorizada com o NEXO. Nenhum dado financeiro foi acessado ou alterado." }] });
  if (m.method === "tools/call" && m.params?.name === "registrar_lancamento") {
    let body;
    try { body = argumentsForEntry(m.params.arguments); }
    catch (e) { return result({ isError: true, content: [{ type: "text", text: e instanceof Error ? e.message : "Lançamento inválido." }] }); }
    if (!publicKey) return result({ isError: true, content: [{ type: "text", text: "Gravação indisponível: configuração incompleta." }] });
    try {
      // JWT do usuário + chave pública. Nunca utilizar service_role nesta gravação.
      const response = await fetch(internal + "/rest/v1/rpc/nexo_registrar_lancamento", { method: "POST", headers: { apikey: publicKey, Authorization: authorization, "Content-Type": "application/json" }, body: JSON.stringify(body), signal: AbortSignal.timeout(15000) });
      if (!response.ok) return result({ isError: true, content: [{ type: "text", text: "Lançamento não confirmado. Confira os dados e reutilize o mesmo identificador ao tentar novamente. Nenhum registro existente foi substituído." }] });
      const saved = await response.json();
      const label = body.p_tipo === "receita" ? "Receita" : "Despesa";
      const money = (body.p_centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
      return result({ structuredContent: saved, content: [{ type: "text", text: `${label} ${saved.repetido ? "já registrada" : "registrada"}: ${money} · ${body.p_categoria} · ${body.p_data}.` }] });
    } catch {
      return result({ isError: true, content: [{ type: "text", text: "Não foi possível confirmar a gravação. Ao repetir, mantenha o mesmo identificador para evitar duplicação." }] });
    }
  }
  return error(-32601, "Method or tool not found");
});
