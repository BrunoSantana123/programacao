const responseParameters = new Set(['code', 'state', 'error', 'error_description', 'error_uri', 'iss']);

export function validCallback(raw) {
  try {
    const url = new URL(raw);
    return url.protocol === 'https:' && !url.username && !url.password && !url.hash;
  } catch {
    return false;
  }
}

// O destino vem do servidor OAuth, nunca dos parâmetros de entrada desta página.
export function sameCallback(raw, registered, response = false) {
  if (!validCallback(raw) || !validCallback(registered)) return false;
  const url = new URL(raw), trusted = new URL(registered);
  if (url.origin !== trusted.origin || url.pathname !== trusted.pathname) return false;
  if (!response) return url.href === trusted.href;

  // Preserve todos os parâmetros registrados, inclusive valores repetidos e ordem.
  for (const key of new Set(trusted.searchParams.keys())) {
    if (JSON.stringify(url.searchParams.getAll(key)) !== JSON.stringify(trusted.searchParams.getAll(key))) return false;
  }
  for (const key of new Set(url.searchParams.keys())) {
    if (trusted.searchParams.has(key)) continue;
    if (!responseParameters.has(key) || url.searchParams.getAll(key).length !== 1) return false;
  }
  const code = url.searchParams.get('code'), error = url.searchParams.get('error');
  return Boolean(code) !== Boolean(error);
}
