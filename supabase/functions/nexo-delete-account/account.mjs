export async function deleteOwnAccount({authorization,body},auth){
 const deny=(status,message)=>({status,body:{message}});
 if(typeof authorization!=="string"||!/^Bearer [^\s]+$/.test(authorization))return deny(401,"Entre novamente.");
 if(!body||typeof body!=="object"||Array.isArray(body)||Object.keys(body).some(k=>!["password","confirmation"].includes(k))||typeof body.password!=="string"||!body.password||body.password.length>1024||body.confirmation!=="EXCLUIR")return deny(400,"Confirme a exclusão e informe sua senha.");
 const user=await auth.current(authorization);
 if(!user?.id||!user.email)return deny(401,"Sessão inválida.");
 const reauth=await auth.reauthenticate(user.email,body.password);
 if(!reauth?.user?.id||reauth.user.id!==user.id)return deny(403,"Não foi possível confirmar sua identidade.");
 if(reauth.user.id!==user.id)return deny(403,"Conta divergente.");
 const result=await auth.remove(user.id);
 if(!result)return deny(502,"A exclusão não foi confirmada. Consulte o suporte antes de repetir.");
 return {status:200,body:{deleted:true}};
}
