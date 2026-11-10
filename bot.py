import json
from datetime import datetime

def carregar_leads():
    try:
        with open("leads.json", "r") as arquivo:
            return json.load(arquivo)
    except FileNotFoundError:
        return []

def salvar_leads(leads):
    with open("leads.json", "w") as arquivo:
        json.dump(leads, arquivo, indent=4, ensure_ascii=False)

RESPOSTAS = {
    ("preço", "preco", "valor", "quanto custa"): "Nosso plano começa em R$ 99/mês. Quer que eu envie os detalhes?",
    ("horário", "horario", "funciona", "aberto"): "Atendemos de segunda a sexta, das 9h às 18h.",
    ("pix", "pagamento", "cartão", "cartao"): "Aceitamos Pix, cartão de crédito e boleto.",
    ("oi", "olá", "ola", "bom dia", "boa tarde", "boa noite"): "Olá! Sou o assistente virtual. Como posso ajudar?",
    ("quero", "comprar", "contratar", "fechar"): "QUENTE",
}

def responder(mensagem):
    texto = mensagem.lower()
    for palavras, resposta in RESPOSTAS.items():
        for palavra in palavras:
            if palavra in texto:
                return resposta
    return "Não entendi bem. Pode me dizer se quer saber sobre preço, horário ou pagamento?"

leads = carregar_leads()
nome = input("Qual seu nome? ")

while True:
    mensagem = input(f"{nome}: ")
    if mensagem.lower() == "sair":
        break

    resposta = responder(mensagem)

    if resposta == "QUENTE":
        print("Bot: Ótimo! Vou te encaminhar para um atendente agora.")
        leads.append({
            "nome": nome,
            "mensagem": mensagem,
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        })
        salvar_leads(leads)
        print("(lead quente salvo em leads.json)")
    else:
        print(f"Bot: {resposta}")
