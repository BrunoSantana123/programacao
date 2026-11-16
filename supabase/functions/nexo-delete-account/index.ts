import { deleteOwnAccount } from "./account.mjs";
const allowedOrigin = "https://brunosantana123.github.io";
const cors = {"Access-Control-Allow-Origin":allowedOrigin,"Vary":"Origin","Access-Control-Allow-Methods":"POST, OPTIONS","Access-Control-Allow-Headers":"authorization, apikey, content-type, x-client-info","Cache-Control":"no-store"};
const json = (body:unknown,status=200) => new Response(JSON.stringify(body),{status,headers:{...cors,"Content-Type":"application/json"}});
Deno.serve(async (req) => {
  if(req.headers.get("origin")!==allowedOrigin)return json({message:"Origem não autorizada."},403);
  if(req.method==="OPTIONS")return new Response(null,{status:204,headers:cors});
  if(req.method!=="POST")return json({message:"Método não permitido."},405);
  try{
    const raw=await req.text(); if(raw.length>8192)return json({message:"Solicitação inválida."},400);
    let body; try{body=JSON.parse(raw)}catch{return json({message:"Solicitação inválida."},400)}
    const url=Deno.env.get("SUPABASE_URL"), anon=Deno.env.get("SUPABASE_ANON_KEY"), service=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    if(!url||!anon||!service)return json({message:"Serviço indisponível."},503);
    const current=async (authorization:string)=>{
      const res=await fetch(url+"/auth/v1/user",{headers:{apikey:anon,Authorization:authorization},cache:"no-store"});
      return res.ok?await res.json():null;
    };
    const reauthenticate=async (email:string,password:string)=>{
      const res=await fetch(url+"/auth/v1/token?grant_type=password",{method:"POST",headers:{apikey:anon,"Content-Type":"application/json"},body:JSON.stringify({email,password})});
      if(!res.ok)return null;
      const value=await res.json();
      // The password grant creates a separate session. Revoke only that session; never log tokens.
      if(value.access_token)try{await fetch(url+"/auth/v1/logout?scope=local",{method:"POST",headers:{apikey:anon,Authorization:"Bearer "+value.access_token}})}catch{/* no secret logging */}
      return {user:value.user};
    };
    const remove=async (id:string)=>{
      const res=await fetch(url+"/auth/v1/admin/users/"+encodeURIComponent(id),{method:"DELETE",headers:{apikey:service,Authorization:"Bearer "+service,"Content-Type":"application/json"},body:JSON.stringify({should_soft_delete:false})});
      return res.ok;
    };
    const result=await deleteOwnAccount({authorization:req.headers.get("authorization"),body},{current,reauthenticate,remove});
    return json(result.body,result.status);
  }catch{return json({message:"Não foi possível confirmar a exclusão. Consulte o suporte."},503)}
});
