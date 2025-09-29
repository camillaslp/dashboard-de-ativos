import streamlit as st
st.set_page_config(layout="wide")
import yfinance as yf
import json
import os
import warnings
from google.oauth2.service_account import Credentials
import gspread
warnings.filterwarnings("ignore", category=FutureWarning)

# ------------------- Carregar credenciais -------------------
try:
    creds_dict = json.loads(st.secrets["GOOGLE_CREDS"])
except KeyError:
    st.error("Chave 'GOOGLE_CREDS' não encontrada em st.secrets")
    st.stop()
except json.JSONDecodeError as e:
    st.error(f"Erro ao decodificar JSON das credenciais: {e}")
    st.stop()

# ------------------- Conectar ao Google Sheets -------------------
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

try:
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
except Exception as e:
    st.error(f"Erro ao autenticar no Google Sheets: {e}")
    st.stop()
    
# ------------------- Abrir planilha específica -------------------
planilha_nome = "Acoes"  # Alterar para o nome correto
try:
    sheet = client.open(planilha_nome).sheet1
    st.success(f"Planilha '{planilha_nome}' aberta com sucesso!")
except gspread.exceptions.SpreadsheetNotFound:
    st.error(f"Planilha '{planilha_nome}' não encontrada. "
             "Verifique se o nome está correto e se foi compartilhada com o Service Account.")
except gspread.exceptions.APIError as e:
    st.error(f"Erro de API ao abrir a planilha '{planilha_nome}': {e}")


# --------------- Config ----------------
ARQUIVO_ACOES = "acoes.json"


# --------------- Utils -----------------
def carregar_json(path):
    if os.path.exists(path):
        if os.path.getsize(path) > 0:
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


def avaliar_alerta(preco_atual, preco_teto):
    if preco_atual < preco_teto:
        return "🟢 Oportunidade", "green"
    elif preco_atual > preco_teto * 1.1:
         return "🔴 Acima do Teto", "red"
    return "Manter Posição", "gray"


# --------------- Painel Ações ----------------
def painel_acoes():
    st.title("📊 Dashboard de Ações")
    ativos = carregar_json(ARQUIVO_ACOES)

    with st.sidebar:
        st.header("⚙️ Gerenciar Ativos")
        with st.expander("➕ Cadastrar Ação", expanded=False):
            codigo_input = st.text_input("Código do Ativo (ex: PETR4)", key="cad_cod")
            preco_medio = st.number_input("Preço Médio", min_value=0.0, step=0.01, key="cad_medio")
            preco_teto = st.number_input("Preço Teto", min_value=0.0, step=0.01, key="cad_teto")
            if st.button("Salvar Ação", key="btn_salvar_acao"):
                codigo = normalizar_codigo(codigo_input)
                if codigo:
                    try:
                        tk = yf.Ticker(codigo)
                        if not tk.history(period="5d").empty:
                            ativos[codigo] = {"preco_medio": preco_medio, "preco_teto": preco_teto}
                            salvar_json(ARQUIVO_ACOES, ativos)
                            st.success(f"{codigo} salvo!")
                            st.rerun()
                        else:
                            st.error("Código inválido ou sem dados.")
                    except Exception as e:
                        st.error(f"Erro ao validar o código: {e}")

        if ativos:
            with st.expander("✏️ Editar Ação", expanded=False):
                ativo_ed = st.selectbox("Selecione o Ativo", list(ativos.keys()), key="edicao_acao")
                novo_med = st.number_input("Novo Preço Médio", value=ativos[ativo_ed]["preco_medio"], step=0.01, key="novo_med")
                novo_teto = st.number_input("Novo Preço Teto", value=ativos[ativo_ed]["preco_teto"], step=0.01, key="novo_teto")
                if st.button("Atualizar Ação", key="btn_atualizar_acao"):
                    ativos[ativo_ed]["preco_medio"] = novo_med
                    ativos[ativo_ed]["preco_teto"] = novo_teto
                    salvar_json(ARQUIVO_ACOES, ativos)
                    st.success("Atualizado!")
                    st.rerun()

            with st.expander("🗑️ Excluir Ação", expanded=False):
                ativo_exc = st.selectbox("Selecione para Excluir", list(ativos.keys()), key="excluir_acao")
                if st.button("Remover", key="btn_excluir_acao"):
                    del ativos[ativo_exc]
                    salvar_json(ARQUIVO_ACOES, ativos)
                    st.warning(f"{ativo_exc} removido!")
                    st.rerun()


    if not ativos:
        st.info("Nenhuma ação cadastrada. Adicione uma na barra lateral.")
        return

    codigos_str = " ".join(ativos.keys())
    dados_acoes = yf.download(codigos_str, period="2d", interval="5d", progress=False, group_by='ticker')
    
    if dados_acoes.empty and len(ativos) > 0:
        st.error("Não foi possível buscar os dados das ações.")
        return

    cols = st.columns(5)
    i = 0
    for codigo, info in ativos.items():
        try:
            if len(ativos) == 1:
                dados_ativo = dados_acoes
            else:
                dados_ativo = dados_acoes[codigo]

            if dados_ativo.empty or dados_ativo['Close'].isnull().all():
                with cols[i % 5]:
                    st.warning(f"Sem dados para {codigo.replace('.SA', '')}")
                i += 1
                continue

            preco_atual = float(dados_ativo["Close"].iloc[-1])
            preco_anterior = float(dados_ativo["Close"].iloc[-2]) if len(dados_ativo) > 1 else preco_atual
            variacao = ((preco_atual - preco_anterior) / preco_anterior) * 100 if preco_anterior else 0
            mensagem, cor_borda = avaliar_alerta(preco_atual, info["preco_teto"])

            with cols[i % 5]:
                # O HTML a ser renderizado é definido aqui
                html_card = f"""
                
                <div style="border:7px solid {cor_borda}; border-radius:10px; 
                            padding:20px; margin-bottom:55px; height:250px; 
                            display:flex; flex-direction:column; justify-content:space-between;
                            box-shadow: 0 5px 8px 0 rgba(0,0,0,0.2);">
                    <h4 style="text-align:center; margin-top:-20px; margin-bottom:-2px;">{codigo.replace(".SA", "")}</h4>
                    <div style="background-color:{cor_borda}; color:white; text-align:center; 
                                padding:5px; border-radius:5px; font-weight:bold;">
                        {mensagem}
                    </div>
                    <b>Preço Atual: R$ {preco_atual:.2f}</b>
                    Preço Médio: R$ {info['preco_medio']:.2f}
                    <p>Preço Teto: R$ {info['preco_teto']:.2f}</p>
                    <p>Variação D-1: <span style="color:{'green' if variacao >= 0 else 'red'}; font-weight:bold;">
                        {'▲' if variacao >= 0 else '▼'} {variacao:.2f}%
                    </span></p>  
                </div>
                """
                st.markdown(html_card, unsafe_allow_html=True)
                
                
            i += 1
        
        except Exception as e:
            with cols[i % 5]:
                 st.error(f"Erro no card de {codigo.replace('.SA', '')}")
            i+=1
# --------------- Main ----------------

painel_acoes()









