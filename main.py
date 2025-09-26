try:
    import importlib.metadata
except ImportError:
    import importlib_metadata as importlib_metadata
import streamlit as st
import yfinance as yf
import json, os, sys, re
from datetime import datetime
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------- Função para arquivos em PyInstaller ----------------
def resource_path(relative_path):
    """Retorna o caminho absoluto do arquivo, compatível com PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ---------------- Arquivos JSON ----------------
ARQUIVO_ACOES = resource_path("acoes.json")
ARQUIVO_OPCOES = resource_path("opcoes.json")

# ---------------- Estilo Global ----------------
st.markdown("""
    <style>
    .card {
        border: 1px solid gray;
        border-radius: 6px;
        padding: 4px;
        margin: 4px;
        max-width: 220px;
        font-size: 13px;
        justify-content: center;
        align-items: center;
        text-align: center;
    }
    .card h4 {
        font-size: 15px;
        margin: 0 0 4px 0;
        justify-content: center;
        align-items: center;
        text-align: center;
    }
    .card p {
        margin: 0;
        justify-content: center;
        align-items: center;
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------- Utils -----------------
def carregar_json(path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def salvar_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

def normalizar_codigo(codigo):
    c = codigo.strip().upper()
    if c and not c.endswith(".SA"):
        c += ".SA"
    return c

def avaliar_alerta(preco_atual, preco_medio, preco_teto, variacao_dia):
    if preco_atual < preco_teto:
        return "🟢 Sinal de Compra", "green"
    if abs(variacao_dia) >= 20:
        return "⚠️ Atenção: Variação Alta", "yellow"
    return "Manter", "gray"

# ---------------- Decodificar opção B3 -----------------
def decodificar_opcao(codigo: str):
    codigo = codigo.strip().upper()
    m = re.match(r"^([A-Z]{4})([A-Z])(\d+)$", codigo)
    if not m:
        st.error(f"Código inválido: {codigo}")
        return None

    base, letra, numero = m.groups()
    numero = int(numero)

    meses_call = "ABCDEFGHIJKL"  # Call A-L
    meses_put  = "MNOPQRSTUVWX"  # Put M-X

    if letra in meses_call:
        tipo = "call"
        mes = meses_call.index(letra) + 1
    elif letra in meses_put:
        tipo = "put"
        mes = meses_put.index(letra) + 1
    else:
        st.error(f"Letra de vencimento inválida: {letra}")
        return None

    ano = datetime.today().year
    if mes < datetime.today().month:
        ano += 1
    vencimento = datetime(ano, mes, 15)

    strike = numero / 10 if numero < 1000 else numero / 100

    return {
        "codigo": codigo,
        "base": base + ".SA",
        "tipo": tipo,
        "vencimento": vencimento.strftime("%Y-%m-%d"),
        "strike": strike
    }

# ---------------- Último fechamento da opção -----------------
def ultimo_fechamento_opcao(base, tipo, strike, vencimento):
    try:
        tk = yf.Ticker(base)
        if vencimento not in tk.options:
            return None
        chain = tk.option_chain(vencimento)
        tabela = chain.calls if tipo == "call" else chain.puts
        linha = tabela.loc[tabela["strike"] == strike]
        if linha.empty:
            return None
        return float(linha["lastPrice"].values[0])
    except Exception:
        return None

# ---------------- Indicador de valor intrínseco -----------------
def indicador_opcao(preco_ativo, strike, tipo, premio_pago):
    if tipo == "call":
        valor_intrinseco = max(0, preco_ativo - strike)
    else:
        valor_intrinseco = max(0, strike - preco_ativo)

    retorno_pct = ((valor_intrinseco - premio_pago) / premio_pago * 100) if premio_pago else 0

    if valor_intrinseco == 0:
        status = "Out of the money"
        cor = "red"
    elif valor_intrinseco < premio_pago:
        status = "Opção cara"
        cor = "red"
    elif valor_intrinseco > premio_pago:
        status = "Opção barata"
        cor = "green"
    else:
        status = "Justa"
        cor = "yellow"

    return valor_intrinseco, retorno_pct, status, cor

# ---------------- Painel Opções -----------------
def painel_opcoes():
    st.sidebar.header("📌 Opções")
    opcoes = carregar_json(ARQUIVO_OPCOES)

    # --- Cadastrar ---
    with st.sidebar.expander("➕ Cadastrar Opção", expanded=False):
        codigo_input = st.text_input("Código da Opção (ex: PETRF25)")
        preco_medio = st.number_input("Preço Pago (R$)", min_value=0.0, step=0.01, key="pm_opc")
        preco_obj = st.number_input("Preço Objetivo (R$)", min_value=0.0, step=0.01, key="po_opc")

        if st.button("Salvar Opção"):
            info = decodificar_opcao(codigo_input)
            if info:
                preco_atual = ultimo_fechamento_opcao(info["base"], info["tipo"], info["strike"], info["vencimento"])
                key = info["codigo"]
                opcoes[key] = {
                    **info,
                    "preco_medio": preco_medio,
                    "preco_objetivo": preco_obj,
                    "ultimo_fechamento": preco_atual
                }
                salvar_json(ARQUIVO_OPCOES, opcoes)
                st.success(f"Opção {key} salva! Último preço: {preco_atual}")

    # --- Exibição principal ---
    st.subheader("📌 Opções Cadastradas")
    if opcoes:
        cols = st.columns(4)
        i = 0
        for k, opt in opcoes.items():
            if not all(x in opt for x in ("base","tipo","strike","vencimento")):
                st.warning(f"Opção {k} ignorada: dados incompletos")
                continue

            try:
                dados_ativo = yf.download(opt["base"], period="2d", interval="1d", progress=False)
                preco_ativo = float(dados_ativo["Close"].iloc[-1])
            except:
                preco_ativo = 0

            preco_opcao = opt.get("ultimo_fechamento") or 0
            valor_intrinseco, retorno_pct, status, cor = indicador_opcao(preco_ativo, opt["strike"], opt["tipo"], opt["preco_medio"])

            cols[i % 4].markdown(
                f"""
                <div style="border:2px solid {cor}; border-radius:6px; padding:6px; margin:3px">
                    <h4>{k}</h4>
                    <p>Tipo: {opt['tipo']}</p>
                    <p>Strike: {opt['strike']}</p>
                    <p>Venc: {opt['vencimento']}</p>
                    <p>Último preço opção: R$ {preco_opcao:.2f}</p>
                    <p>Preço ativo: R$ {preco_ativo:.2f}</p>
                    <p>Valor Intrínseco: R$ {valor_intrinseco:.2f}</p>
                    <p>Retorno sobre prêmio: {retorno_pct:.2f}%</p>
                    <b style="color:{cor}">{status}</b>
                </div>
                """,
                unsafe_allow_html=True
            )
            i += 1
    else:
        st.info("Nenhuma opção cadastrada.")

# ---------------- Painel Ações -----------------
def painel_acoes():
    ativos = carregar_json(ARQUIVO_ACOES)

    # --- Cadastrar ---
    with st.sidebar.expander("➕ Cadastrar", expanded=False):
        codigo_input = st.text_input("Código (ex: PETR4)")
        preco_medio = st.number_input("Preço Médio", min_value=0.0, step=0.01, key="cad_medio")
        preco_teto = st.number_input("Preço Teto", min_value=0.0, step=0.01, key="cad_teto")

        if st.button("Salvar Ação"):
            codigo = normalizar_codigo(codigo_input)
            if codigo:
                dados = yf.download(codigo, period="2d", interval="1d", progress=False)
                if dados.empty:
                    st.error("Código inválido ou sem dados.")
                else:
                    ativos[codigo] = {"preco_medio": preco_medio, "preco_teto": preco_teto}
                    salvar_json(ARQUIVO_ACOES, ativos)
                    st.success(f"{codigo} salvo!")

    # --- Exibição principal ---
    st.subheader("📌 Ações Cadastradas")
    if ativos:
        cols = st.columns(4)
        i = 0
        for codigo, info in ativos.items():
            dados = yf.download(codigo, period="5d", interval="1d", progress=False)
            if dados.empty:
                st.warning(f"Sem dados para {codigo}")
                continue

            preco_atual = float(dados["Close"].iloc[-1])
            preco_anterior = float(dados["Close"].iloc[-2]) if len(dados) > 1 else preco_atual
            variacao = ((preco_atual - preco_anterior) / preco_anterior) * 100

            mensagem, cor = avaliar_alerta(preco_atual, info["preco_medio"], info["preco_teto"], variacao)

            cols[i % 4].markdown(
                f"""
                <div class="card" style="border-color:{cor}">
                    <h4>{codigo}</h4>
                    <p>Atual: R$ {preco_atual:.2f}</p>
                    <p>Médio: R$ {info['preco_medio']:.2f}</p>
                    <p>Teto: R$ {info['preco_teto']:.2f}</p>
                    <p>Variação: {variacao:.2f}%</p>
                    <b style="color:{cor}">{mensagem}</b>
                </div>
                """,
                unsafe_allow_html=True
            )
            i += 1
    else:
        st.info("Nenhuma ação cadastrada.")

# ---------------- Main -----------------
st.title("📊 Dashboard Financeiro")
modo = st.radio("Selecione painel:", ["Ações", "Opções"], horizontal=True)

if modo == "Ações":
    painel_acoes()
else:
    painel_opcoes()

# ---------------- Executar Streamlit quando for .exe -----------------
if __name__ == "__main__":
    import streamlit.web.cli as stcli
    sys.argv = ["streamlit", "run", os.path.abspath(__file__), "--server.port=8501"]
    sys.exit(stcli.main())
