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
  const auth = (...args) => window.NexoAuth.request(...args);
  const failure = (...args) => window.NexoAuth.errorMessage(...args);
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
    if (!window.NexoAuth.strongPassword(password)) {
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
    lock(true); $('requestView').hidden = true; message('Verificando seu link…');
    try {
      const result = await window.NexoAuth.verifyLink('recovery');
      if (!result) { forget(); message(''); return; }
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
