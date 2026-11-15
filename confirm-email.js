'use strict';
(async () => {
  const message = document.getElementById('message');
  try {
    const result = await NexoAuth.verifyLink('signup');
    if (!result) { message.textContent = 'Abra o link enviado para seu e-mail. Para outro link, use Reenviar confirmação na tela de entrada.'; return; }
    // Confirmação não inicia sessão no aplicativo nem persiste o token.
    try { await NexoAuth.request('logout', null, result.access_token, 'POST', '?scope=local'); } catch {}
    message.textContent = 'E-mail confirmado com sucesso. Entre com seu e-mail e senha.';
  } catch (error) {
    message.classList.add('error'); message.textContent = NexoAuth.errorMessage(error, true);
  }
})();
