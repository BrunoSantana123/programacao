'use strict';
window.NexoAuth = (() => {
  const passwordMessage = 'Use de 12 a 128 caracteres, com maiúsculas, minúsculas, números e símbolos, sem espaços nas pontas.';
  function strongPassword(value) {
    return typeof value === 'string' && value.length >= 12 && value.length <= 128 &&
      /[a-z]/.test(value) && /[A-Z]/.test(value) && /[0-9]/.test(value) &&
      /[^a-zA-Z0-9\s]/.test(value) && value.trim() === value;
  }
  function target(page) {
    const u = new URL(page, location.href); u.search = ''; u.hash = ''; return u.href;
  }
  async function request(path, body, token, method = 'POST', query = '') {
    const c = window.NEXO_AUTH_CONFIG;
    if (!c?.supabaseUrl || !c?.publishableKey) throw Error('config');
    const u = new URL(c.supabaseUrl);
    if ((u.protocol !== 'https:' && !['localhost','127.0.0.1'].includes(u.hostname)) ||
        u.pathname !== '/' || u.search || u.hash || u.username || u.password) throw Error('config');
    const res = await fetch(c.supabaseUrl + '/auth/v1/' + path + query, {
      method, cache: 'no-store', referrerPolicy: 'no-referrer', signal: AbortSignal.timeout(20000),
      headers: {apikey: c.publishableKey, 'Content-Type': 'application/json',
        ...(token ? {Authorization: 'Bearer ' + token} : {})},
      ...(body ? {body: JSON.stringify(body)} : {})
    });
    let data = {}; try { data = await res.json(); } catch {}
    if (!res.ok) { const error = Error('auth'); error.status = res.status; error.code = data.error_code || data.code; throw error; }
    return data;
  }
  function errorMessage(error, link = false) {
    if (error.message === 'config') return 'O acesso ainda não foi configurado. Tente novamente mais tarde.';
    if (error.status === 429 || ['over_email_send_rate_limit','over_request_rate_limit'].includes(error.code)) return 'Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.';
    if (error.code === 'email_not_confirmed') return 'Confirme seu e-mail antes de entrar. Use Reenviar confirmação se precisar de outro link.';
    if (['weak_password','same_password'].includes(error.code)) return 'Escolha uma senha forte e diferente da anterior. ' + passwordMessage;
    if (error.code === 'invalid_credentials') return 'E-mail ou senha incorretos.';
    if (error.status >= 500) return 'Não foi possível concluir no serviço de acesso. Tente novamente mais tarde. Se persistir, entre em contato com o suporte.';
    if (link && [400,401,403,422].includes(error.status)) return 'Este link é inválido, já foi utilizado ou expirou. Solicite um novo link.';
    if (error.code === 'signup_disabled') return 'Novos cadastros estão temporariamente indisponíveis.';
    return 'Não foi possível concluir agora. Confira os dados e sua conexão e tente novamente.';
  }
  async function verifyLink(expected) {
    const params = new URLSearchParams(location.search), fragment = new URLSearchParams(location.hash.slice(1));
    history.replaceState(null, '', location.pathname);
    if (!params.size && !fragment.size) return null;
    if (params.has('error') || fragment.has('error')) throw Object.assign(Error('auth'), {status:403});
    const hashed = params.get('token_hash');
    let result;
    if (!fragment.size && params.getAll('type').length === 1 && params.get('type') === expected &&
        params.getAll('token_hash').length === 1 && /^[a-f0-9]{32,256}$/i.test(hashed || '')) {
      result = await request('verify', {type: expected, token_hash: hashed});
    } else if (!params.size && fragment.get('type') === expected && fragment.getAll('type').length === 1 &&
               fragment.getAll('access_token').length === 1 && fragment.get('access_token')?.length <= 16384 &&
               /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(fragment.get('access_token') || '')) {
      // O fragmento não é confiável: verificar a sessão no Supabase antes de usá-la.
      const access = fragment.get('access_token');
      const user = await request('user', null, access, 'GET');
      result = {user, access_token:access, expires_in: Number(fragment.get('expires_in'))};
    } else throw Object.assign(Error('auth'), {status:403});
    if (!result.access_token || !result.user?.id || !Number.isFinite(result.expires_in) || result.expires_in <= 0) {
      throw Object.assign(Error('auth'), {status:403});
    }
    if (expected === 'signup' && !result.user.email_confirmed_at) throw Object.assign(Error('auth'), {status:403});
    return result;
  }
  return Object.freeze({request, target, strongPassword, passwordMessage, errorMessage, verifyLink});
})();
// Compatibilidade com links padrão quando o Supabase usa a Site URL como destino.
if (['/','/index.html','/nexo-teste.html'].some(suffix => location.pathname.endsWith(suffix))) {
  const hash = new URLSearchParams(location.hash.slice(1)), query = new URLSearchParams(location.search);
  const type = hash.get('type') || query.get('type');
  if (['signup','recovery'].includes(type) && (hash.has('access_token') || hash.has('error') || query.has('token_hash'))) {
    const destination = new URL(type === 'recovery' ? './recuperar.html' : './confirmar.html', location.href);
    destination.search = location.search; destination.hash = location.hash;
    location.replace(destination.href);
  }
}
