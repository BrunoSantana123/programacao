from datetime import datetime
import json

RESPOSTAS = {
    ("preço", "preco", "valor", "quanto custa"):
        "Nosso plano começa em R$ 99/mês.",
    ("horário", "horario", "funciona", "aberto"):
        "Atendemos de segunda a sexta, das 9h às 18h.",
    ("pix", "pagamento", "cartão", "cartao"):
        "Aceitamos Pix, cartão e boleto.",
    ("oi", "olá", "ola", "bom dia", "boa tarde", "boa noite"):
        "Olá! Sou o assistente virtual. Como posso ajudar?",
    ("quero", "comprar", "contratar", "fechar"):
        "QUENTE",
}


def carregar(arquivo):
    try:
        with open(arquivo, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def salvar(arquivo, dados):
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)


def responder(mensagem):
    texto = mensagem.lower()
    for palavras, resposta in RESPOSTAS.items():
        for palavra in palavras:
            if palavra in texto:
                return resposta
    return "Não entendi. Pergunte sobre preço, horário ou pagamento."


def pedir_telefone():
    while True:
        telefone = input("Seu telefone com DDD: ")
        numeros = ""
        for c in telefone:
            if c.isdigit():
                numeros = numeros + c
        if len(numeros) >= 10:
            return numeros
        print("Telefone inválido. Exemplo: 21999998888")


def relatorio(leads):
    if not leads:
        print("Nenhum lead quente ainda.")
        return
    print("")
    print("=== LEADS QUENTES ===")
    print("Total:", len(leads))
    for lead in leads:
        print("-", lead["nome"], lead["telefone"], lead["data"])
        print("  Disse:", lead["mensagem"])


def agora():
    return datetime.now().strftime("%d/%m/%Y %H:%M")


leads = carregar("leads.json")
historico = carregar("historico.json")

nome = input("Qual seu nome? ").strip()
telefone = pedir_telefone()
print("")
print("Conversa iniciada.")
print("Digite relatorio para ver os leads ou sair para encerrar.")
print("")

while True:
    mensagem = input(nome + ": ").strip()

    if mensagem.lower() == "sair":
        break

    if mensagem.lower() == "relatorio":
        relatorio(leads)
        continue

    resposta = responder(mensagem)
    historico.append({"quem": nome, "texto": mensagem, "hora": agora()})

    if resposta == "QUENTE":
        resposta = "Ótimo! Vou te encaminhar para um atendente agora."
        leads.append({
            "nome": nome,
            "telefone": telefone,
            "mensagem": mensagem,
            "data": agora(),
        })
        salvar("leads.json", leads)
        print("(lead quente salvo)")

    print("Bot: " + resposta)
    historico.append({"quem": "Bot", "texto": resposta, "hora": agora()})
    salvar("historico.json", historico)