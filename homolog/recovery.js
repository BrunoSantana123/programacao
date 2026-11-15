'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let recovery = null, busy = false, expires = 0, timer = null;
  function message(text, error = false) {
    $('message').textContent = text;
    $('message').classList.toggle('error', error);
  }
  function lock(value) {
    busy = value;
    document.querySelectorAll('button').forEach(button => { button.disabled = value; });
  }
  function forget() {
    recovery = null; expires = 0; clearTimeout(timer);
    $('resetForm').reset(); $('resetView').hidden = true;
    $('requestView').hidden = false;
  }
  function config() {
    const c = window.NEXO_HOMOLOG;
    if (!c?.supabaseUrl || !c?.publishableKey) throw Error('config');
    const u = new URL(c.supabaseUrl);
    if (u.hostname === 'tznebgdgdqpbhjdrhprb.supabase.co' ||
        (u.protocol !== 'https:' && !['localhost', '127.0.0.1'].includes(u.hostname)) ||
        u.pathname !== '/' || u.search || u.hash || u.username || u.password) throw Error('config');
    return c;
  }
  async function auth(path, body, token, method = 'POST', query = '') {
    const c = config();
    const res = await fetch(c.supabaseUrl + '/auth/v1/' + path + query, {
      method, cache: 'no-store', referrerPolicy: 'no-referrer',
      signal: AbortSignal.timeout(20000),
      headers: {apikey: c.publishableKey, 'Content-Type': 'application/json',
        ...(token ? {Authorization: 'Bearer ' + token} : {})},
      ...(body ? {body: JSON.stringify(body)} : {})
    });
    let data = {}; try { data = await res.json(); } catch {}
    if (!res.ok) { const error = Error('auth'); error.status = res.status; error.code = data.error_code || data.code; throw error; }
    return data;
  }
  function failure(error, link = false) {
    if (error.message === 'config') return 'A recuperação ainda não foi configurada na homologação. Tente novamente mais tarde.';
    if (error.status === 429 || error.code === 'over_email_send_rate_limit') return 'Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.';
    if (['weak_password', 'same_password'].includes(error.code)) return 'Escolha uma senha forte e diferente da anterior.';
    if (link && [400, 401, 403, 422].includes(error.status)) return 'Este link é inválido, já foi utilizado ou expirou. Solicite um novo link abaixo.';
    return 'Não foi possível concluir agora. Verifique sua conexão e tente novamente. Se persistir, entre em contato com o suporte.';
  }
  $('requestForm').onsubmit = async event => {
    event.preventDefault(); if (busy) return; lock(true);
    message('Enviando solicitação…');
    try {
      const email = String(new FormData(event.currentTarget).get('email')).trim();
      const target = new URL('./recuperar.html', location.href); target.search = ''; target.hash = '';
      await auth('recover', {email}, null, 'POST', '?redirect_to=' + encodeURIComponent(target.href));
      message('Se houver uma conta com esse e-mail, você receberá um link de recuperação. Confira também o spam.');
      event.target.reset();
    } catch (error) { message(failure(error), true); }
    finally { lock(false); }
  };
  $('resetForm').onsubmit = async event => {
    event.preventDefault(); if (busy) return;
    if (!recovery || Date.now() >= expires) { forget(); message('O prazo para redefinir a senha terminou. Solicite um novo link.', true); return; }
    const form = new FormData(event.currentTarget), password = String(form.get('password'));
    if (password !== form.get('confirmation')) { message('As senhas não coincidem.', true); return; }
    if (password.length < 12 || password.length > 128 || !/[a-z]/.test(password) || !/[A-Z]/.test(password) || !/[0-9]/.test(password) || !/[^a-zA-Z0-9\s]/.test(password) || password.trim() !== password) {
      message('Use de 12 a 128 caracteres, com maiúsculas, minúsculas, números e símbolos, sem espaços nas pontas.', true); return;
    }
    lock(true); message('Salvando nova senha…');
    try {
      const current = recovery;
      await auth('user', {password}, current, 'PUT');
      // Revoga as sessões existentes; nunca transforma a recuperação em login no app.
      let revoked = true;
      try { await auth('logout', null, current, 'POST', '?scope=global'); } catch { revoked = false; }
      forget(); $('requestView').hidden = true;
      message(revoked ? 'Senha alterada com sucesso. Entre novamente com sua nova senha.' : 'Senha alterada. Não foi possível confirmar o encerramento das outras sessões; entre em contato com o suporte se suspeitar de acesso indevido.');
    } catch (error) {
      if ([401, 403].includes(error.status)) forget();
      message(failure(error, true), true);
    } finally { lock(false); }
  };
  async function start() {
    const params = new URLSearchParams(location.search), fragment = new URLSearchParams(location.hash.slice(1));
    // Remove o segredo antes de qualquer pedido de rede. Não usa armazenamento persistente.
    history.replaceState(null, '', location.pathname);
    if (!params.size && !fragment.size) return;
    if (params.get('error') || fragment.get('error')) { message('Este link é inválido ou expirou. Solicite um novo link.', true); return; }
    if (params.get('type') !== 'recovery' || !/^[a-f0-9]{32,256}$/i.test(params.get('token_hash') || '') || fragment.size || params.getAll('token_hash').length !== 1 || params.getAll('type').length !== 1) {
      message('Link de recuperação inválido ou incompatível. Solicite um novo link. Se persistir, informe o suporte.', true); return;
    }
    lock(true); $('requestView').hidden = true; message('Verificando seu link…');
    try {
      const result = await auth('verify', {type: 'recovery', token_hash: params.get('token_hash')});
      if (!result.access_token || !result.user?.id || !Number.isFinite(result.expires_in) || result.expires_in <= 0) throw Error('invalid');
      recovery = result.access_token;
      expires = Date.now() + Math.min(result.expires_in * 1000, 15 * 60 * 1000);
      timer = setTimeout(() => { forget(); message('O prazo para redefinir a senha terminou. Solicite um novo link.', true); }, expires - Date.now());
      $('resetView').hidden = false; message('Link verificado. Cadastre sua nova senha.'); $('resetForm').elements.password.focus();
    } catch (error) { forget(); message(failure(error, true), true); }
    finally { lock(false); }
  }
  window.addEventListener('pagehide', forget);
  window.addEventListener('pageshow', event => { if (event.persisted) forget(); });
  start();
})();
