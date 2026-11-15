// Identificadores públicos, obtidos do mesmo registro OAuth no Supabase e no ChatGPT.
// Não preencher com Client Secret, access token ou chave service_role.
// Identificadores confirmados pelo responsável pela integração. Não acrescentar utm_source.
// Valores vazios mantêm a autorização bloqueada.
export const TRUSTED_CLIENT_ID = '451c10f2-5062-45a7-b4df-94664ecf212c';
export const TRUSTED_CALLBACK = 'https://chatgpt.com/connector/oauth/jtfRMxXsq31B';
// Uma instalação publicada pode atender muitos usuários com o MESMO cliente.
// Instalações próprias do ChatGPT podem criar outro cliente/callback: registrar o par
// exato no Supabase e aqui; autorizar o mesmo Client ID no servidor MCP.
export const TRUSTED_CLIENTS = [
  {clientId: TRUSTED_CLIENT_ID, callback: TRUSTED_CALLBACK},
];
