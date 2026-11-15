import assert from 'node:assert/strict';
import { randomUUID, randomBytes } from 'node:crypto';
const base = 'https://ywabgfguujgvqtrskswf.supabase.co';
const origin = 'https://brunosantana123.github.io';
const anon = process.env.NEXO_HOMOLOG_ANON_KEY;
const admin = process.env.NEXO_HOMOLOG_SERVICE_ROLE_KEY;
if (!anon || !admin || anon === admin) throw new Error('Configure localmente as duas chaves de HOMOLOGAÇÃO. Não envie chaves pelo chat.');
const created = new Set();
async function request(path, {method='GET', key=anon, token, body, prefer}={}) {
  const r = await fetch(base+path,{method, headers:{apikey:key,Authorization:'Bearer '+(token||key),'Content-Type':'application/json',Origin:origin,...(prefer?{Prefer:prefer}:{})},...(body===undefined?{}:{body:JSON.stringify(body)}),redirect:'error',signal:AbortSignal.timeout(20000)});
  const raw=await r.text(); let data; try{data=JSON.parse(raw)}catch{data=null}
  return {status:r.status,ok:r.ok,data};
}
const adminCall=(path,options={})=>request('/auth/v1/admin/users'+path,{...options,key:admin});
const login=(email,password)=>request('/auth/v1/token?grant_type=password',{method:'POST',body:{email,password}});
const dataPath=id=>'/rest/v1/nexo_data?user_id=eq.'+encodeURIComponent(id);
const getData=(u)=>request(dataPath(u.id)+'&select=user_id,data',{token:u.token});
const del=(u,body)=>request('/functions/v1/nexo-delete-account',{method:'POST',token:u.token,body});
const tag=randomUUID();
async function create(label){
  const email='nexo-e2e-'+tag+'-'+label+'@example.com';
  const password='Nx!'+randomBytes(24).toString('hex');
  const result=await adminCall('',{method:'POST',body:{email,password,email_confirm:true}});
  assert.ok(result.ok&&result.data?.id,'criação '+label+': HTTP '+result.status);
  const id=result.data.id;created.add(id);
  const auth=await login(email,password);assert.ok(auth.ok&&auth.data?.access_token&&auth.data?.user?.id===id,'login '+label+': HTTP '+auth.status);
  return {id,email,password,token:auth.data.access_token};
}
async function seed(u,amount){
  const payload={entries:[{id:randomUUID(),date:new Date().toISOString().slice(0,10),type:'income',category:'Teste',amount,description:'Dado sintético'}]};
  const r=await request('/rest/v1/nexo_data',{method:'POST',token:u.token,prefer:'return=representation',body:{user_id:u.id,data:payload}});
  assert.ok(r.ok,'gravação sintética: HTTP '+r.status);const saved=await getData(u);assert.ok(saved.ok&&saved.data?.length===1,'registro sintético não confirmado');return saved.data[0].data;
}
try{
  const a=await create('a'),b=await create('b');console.log('PASS: duas contas descartáveis criadas e autenticadas');
  await seed(a,11);const originalB=await seed(b,22);console.log('PASS: dados sintéticos distintos gravados');
  const cross=await request(dataPath(b.id)+'&select=user_id',{token:a.token});assert.ok(cross.ok&&Array.isArray(cross.data)&&cross.data.length===0,'isolamento de leitura falhou');
  const wrong=await del(a,{password:'invalid-password',confirmation:'EXCLUIR'});assert.equal(wrong.status,403);assert.equal((await getData(a)).data?.length,1);
  const injected=await del(a,{password:a.password,confirmation:'EXCLUIR',user_id:b.id});assert.equal(injected.status,400);
  const missing=await del(a,{password:a.password,confirmation:''});assert.equal(missing.status,400);console.log('PASS: senha incorreta, alvo de terceiro, falta de confirmação e leitura cruzada bloqueados');
  const removed=await del(a,{password:a.password,confirmation:'EXCLUIR'});assert.ok(removed.ok&&removed.data?.deleted===true,'exclusão A não confirmada: HTTP '+removed.status);
  const absent=await adminCall('/'+a.id);assert.equal(absent.status,404,'conta A ainda existe');created.delete(a.id);
  const adminRows=await request(dataPath(a.id)+'&select=user_id',{key:admin});assert.ok(adminRows.ok&&Array.isArray(adminRows.data)&&adminRows.data.length===0,'dados A ainda existem');
  const oldSession=await request('/auth/v1/user',{token:a.token});assert.ok(!oldSession.ok,'token antigo ainda resolve a conta');
  const oldWrite=await request('/rest/v1/nexo_data',{method:'POST',token:a.token,body:{user_id:a.id,data:{entries:[]}}});assert.ok(!oldWrite.ok,'token antigo recriou dados');
  const signIn=await login(a.email,a.password);assert.ok(!signIn.ok,'conta A ainda consegue entrar');
  const afterB=await getData(b);assert.ok(afterB.ok&&afterB.data?.length===1);assert.deepEqual(afterB.data[0].data,originalB);console.log('PASS: conta A e dados removidos, token antigo não recria dados, conta B preservada');
  console.log('PASS: teste de exclusão HTTP em homologação. OAuth MCP e retenção de backups não cobertos.');
}catch(e){console.error('FAIL:',e.message);process.exitCode=1}
finally{for(const id of created){try{const r=await adminCall('/'+id,{method:'DELETE',body:{should_soft_delete:false}});if(!r.ok&&r.status!==404){console.error('Limpeza pendente de conta sintética; HTTP',r.status);process.exitCode=1}}catch{console.error('Não foi possível confirmar limpeza de conta sintética.');process.exitCode=1}}}
