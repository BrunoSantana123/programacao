"""Build estático exclusivo da homologação; nunca usa variáveis de produção."""
import json
import os
from pathlib import Path
import re
import shutil
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = 'tznebgdgdqpbhjdrhprb.supabase.co'


def build(destination=None):
    url = os.environ.get('NEXO_HOMOLOG_SUPABASE_URL', '').rstrip('/')
    key = os.environ.get('NEXO_HOMOLOG_SUPABASE_PUBLISHABLE_KEY', '')
    parsed = urlparse(url)
    if (parsed.scheme != 'https' or not re.fullmatch(r'[a-z0-9]+\.supabase\.co', parsed.netloc)
            or parsed.hostname == PRODUCTION or parsed.path or parsed.query or parsed.fragment):
        raise ValueError('Defina a URL do projeto Supabase exclusivo de homologação.')
    if not re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]+', key):
        raise ValueError('Use somente a chave pública publishable da homologação, nunca uma chave administrativa.')
    target = Path(destination) if destination else ROOT / 'dist-homolog'
    target.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / 'homolog').iterdir():
        if source.is_file() and source.suffix in {'.html', '.js'}:
            shutil.copyfile(source, target / source.name)
    # Preserva a página OAuth existente usando somente identificadores da homologação.
    consent = (ROOT / 'oauth-consent.html').read_text()
    consent = re.sub(r"const PROJECT = '[^']*';", 'const PROJECT = ' + json.dumps(url) + ';', consent)
    consent = re.sub(r"const PUBLISHABLE_KEY = '[^']*';", 'const PUBLISHABLE_KEY = ' + json.dumps(key) + ';', consent)
    (target / 'oauth-consent.html').write_text(consent)
    shutil.copyfile(ROOT / 'oauth-policy.js', target / 'oauth-policy.js')
    client = os.environ.get('NEXO_HOMOLOG_OAUTH_CLIENT_ID', '')
    callback = os.environ.get('NEXO_HOMOLOG_OAUTH_CALLBACK', '')
    if client or callback:
        if not re.fullmatch(r'[a-fA-F0-9-]{36}', client) or not re.fullmatch(r'https://chatgpt\.com/connector/oauth/[A-Za-z0-9_-]+', callback):
            raise ValueError('Identificadores OAuth de homologação inválidos.')
    (target / 'oauth-config.js').write_text('export const TRUSTED_CLIENT_ID = ' + json.dumps(client) + ';\nexport const TRUSTED_CALLBACK = ' + json.dumps(callback) + ';\n')
    config = {'supabaseUrl': url, 'publishableKey': key}
    (target / 'config.js').write_text('window.NEXO_HOMOLOG = Object.freeze(' + json.dumps(config) + ');\n')


if __name__ == '__main__':
    build()
