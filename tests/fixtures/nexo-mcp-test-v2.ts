import { createRemoteJWKSet, jwtVerify } from "npm:jose@6.1.0";
const issuer = "https://tznebgdgdqpbhjdrhprb.supabase.co/auth/v1";
const resource = "https://tznebgdgdqpbhjdrhprb.supabase.co/functions/v1/nexo-mcp-test";
const metadata = resource + "/.well-known/oauth-protected-resource";
const keys = createRemoteJWKSet(new URL(issuer + "/.well-known/jwks.json"));
const scope = "openid";
const schemes = [{type:"oauth2",scopes:[scope]}];
const tool = {name:"testar_conexao",description:"Testa a conexão autorizada com o NEXO. Não consulta nem altera dados financeiros.",inputSchema:{type:"object",properties:{},additionalProperties:false},annotations:{readOnlyHint:true,destructiveHint:false,openWorldHint:false},securitySchemes:schemes,_meta:{securitySchemes:schemes}};
function json(x: unknown, status=200, headers:Record<string,string>={}) {return new Response(JSON.stringify(x),{status,headers:{"Content-Type":"application/json","Cache-Control":"no-store",...headers}});}
function challenge(){return json({error:"unauthorized"},401,{"WWW-Authenticate":'Bearer resource_metadata="'+metadata+'", scope="'+scope+'"'});}
Deno.serve(async(req)=>{
 const url=new URL(req.url);
 if(req.method==="GET" && url.pathname.endsWith("/.well-known/oauth-protected-resource")) return json({resource,authorization_servers:[issuer],scopes_supported:[scope],bearer_methods_supported:["header"]});
 if(req.method!=="POST") return new Response(null,{status:405,headers:{Allow:"POST"}});
 const h=req.headers.get("Authorization");
 if(!h?.startsWith("Bearer ")) return challenge();
 try {
  const {payload}=await jwtVerify(h.slice(7),keys,{issuer,audience:"authenticated",algorithms:["ES256","RS256"],requiredClaims:["exp","sub","iss","aud"]});
  if(payload.role!=="authenticated" || typeof payload.client_id!=="string" || typeof payload.sub!=="string") return challenge();
 }catch{return challenge();}
 let m:any;
 try {m=await req.json();}catch{return json({jsonrpc:"2.0",id:null,error:{code:-32700,message:"Parse error"}},400);}
 if(!m || m.jsonrpc!=="2.0" || typeof m.method!=="string") return json({jsonrpc:"2.0",id:null,error:{code:-32600,message:"Invalid request"}},400);
 if(!Object.prototype.hasOwnProperty.call(m,"id")) return new Response(null,{status:202});
 const result=(r:unknown)=>json({jsonrpc:"2.0",id:m.id,result:r});
 const err=(code:number,message:string)=>json({jsonrpc:"2.0",id:m.id,error:{code,message}});
 if(m.method==="initialize"){const supported=["2025-11-25","2025-06-18","2025-03-26"];return result({protocolVersion:supported.includes(m.params?.protocolVersion)?m.params.protocolVersion:"2025-06-18",capabilities:{tools:{}},serverInfo:{name:"nexo-mcp-test",version:"0.1.1"}});}
 if(m.method==="ping") return result({});
 if(m.method==="tools/list") return result({tools:[tool]});
 if(m.method==="tools/call" && m.params?.name==="testar_conexao") return result({content:[{type:"text",text:"Conexão OAuth autorizada com o NEXO. Nenhum dado financeiro foi acessado ou alterado."}]});
 return err(-32601,"Method or tool not found");
});
