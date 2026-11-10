import json

def carregar():
    try:
        with open("gastos.json", "r") as arquivo:
            return json.load(arquivo)
    except FileNotFoundError:
        return []

def salvar(gastos):
    with open("gastos.json", "w") as arquivo:
        json.dump(gastos, arquivo, indent=4)

def adicionar(gastos):
    descricao = input("Descrição: ")
    valor = float(input("Valor: R$ "))
    categoria = input("Categoria: ")
    gastos.append({"descricao": descricao, "valor": valor, "categoria": categoria})
    salvar(gastos)
    print("Gasto salvo!")

def listar(gastos):
    if not gastos:
        print("Nenhum gasto cadastrado.")
        return
    total = 0
    for gasto in gastos:
        print(f"- {gasto['descricao']} ({gasto['categoria']}): R$ {gasto['valor']:.2f}")
        total += gasto["valor"]
    print(f"Total: R$ {total:.2f}")
def remover(gastos):
    if not gastos:
        print("Nenhum gasto para remover.")
        return
    for i, gasto in enumerate(gastos, start=1):
        print(f"{i} - {gasto['descricao']}: R$ {gasto['valor']:.2f}")
    escolha = input("Número do gasto a remover: ")
    if escolha.isdigit() and 1 <= int(escolha) <= len(gastos):
        removido = gastos.pop(int(escolha) - 1)
        salvar(gastos)
        print(f"Removido: {removido['descricao']}")
    else:
        print("Número inválido.")

def total_por_categoria(gastos):
    if not gastos:
        print("Nenhum gasto cadastrado.")
        return
    totais = {}
    for gasto in gastos:
        categoria = gasto["categoria"]
        totais[categoria] = totais.get(categoria, 0) + gasto["valor"]
    for categoria, valor in totais.items():
        print(f"{categoria}: R$ {valor:.2f}")
gastos = carregar()

while True:
    print("\n1 - Adicionar gasto")
    print("2 - Ver gastos")
    print("3 - Remover gasto")
    print("4 - Total por categoria")
    print("5 - Sair")
    opcao = input("Escolha: ")

    if opcao == "1":
        adicionar(gastos)
    elif opcao == "2":
        listar(gastos)
    elif opcao == "3":
        remover(gastos)
    elif opcao == "4":
        total_por_categoria(gastos)
    elif opcao == "5":
        break
    else:
        print("Opção inválida.")
