import streamlit as st
st.set_page_config(layout="wide")
import yfinance as yf
import json
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

# ------------------- Abrir planilha -------------------
planilha_nome = "Acoes"
try:
    sheet = client.open(planilha_nome).sheet1
    # st.success(f"Planilha '{planilha_nome}' aberta com sucesso!")
except gspread.exceptions.SpreadsheetNotFound:
    st.error(f"Planilha '{planilha_nome}' não encontrada. "
             "Verifique o nome e se compartilhou com o Service Account.")
except gspread.exceptions.APIError as e:
    st.error(f"Erro de API ao abrir a planilha '{planilha_nome}': {e}")

# ------------------- Funções Auxiliares -------------------
def normalizar_codigo(codigo):
    c = str(codigo).strip().upper()
    if c and not c.endswith(".SA"):
        c += ".SA"
    return c

def str_para_float(valor_str):
    """Converte entrada com vírgula para float"""
    if isinstance(valor_str, str):
        return float(valor_str.replace(".", "").replace(",", "."))
    return float(valor_str)

def float_para_str(valor_float):
    """Converte float para string com vírgula e 2 casas decimais"""
    return f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def avaliar_alerta(preco_atual, preco_teto):
    if preco_atual < preco_teto:
        return "🟢 Oportunidade", "green"
    elif preco_atual > preco_teto * 1.1:
        return "🔴 Acima do Teto", "red"
    return "Manter Posição", "gray"

# ------------------- Funções Google Sheets -------------------
def carregar_acoes_google(sheet):
    dados = sheet.get_all_records()
    ativos = {}
    for r in dados:
        codigo = normalizar_codigo(r.get("codigo", ""))
        try:
            preco_medio = str_para_float(r.get("preco_medio", "0"))
        except:
            preco_medio = 0.0
        try:
            preco_teto = str_para_float(r.get("preco_teto", "0"))
        except:
            preco_teto = 0.0
        if codigo:
            ativos[codigo] = {"preco_medio": preco_medio, "preco_teto": preco_teto}
    return ativos

def salvar_acao_google(sheet, codigo, preco_medio, preco_teto):
    """Atualiza ou adiciona ação no Google Sheets"""
    dados = sheet.get_all_records()
    codigo = normalizar_codigo(codigo)
    encontrado = False
    for i, r in enumerate(dados):
        if normalizar_codigo(r["codigo"]) == codigo:
            sheet.update(f"B{i+2}", preco_medio)  # preco_medio como float
            sheet.update(f"C{i+2}", preco_teto)   # preco_teto como float
            encontrado = True
            break
    if not encontrado:
        sheet.append_row([codigo, preco_medio, preco_teto])

def excluir_acao_google(sheet, codigo):
    dados = sheet.get_all_records()
    codigo = normalizar_codigo(codigo)
    for i, r in enumerate(dados):
        if normalizar_codigo(r["codigo"]) == codigo:
            sheet.delete_row(i+2)
            break

# ------------------- Painel de Ações -------------------
def painel_acoes():
    st.title("📊 Dashboard de Ações")
    ativos = carregar_acoes_google(sheet)

    with st.sidebar:
        st.header("⚙️ Gerenciar Ativos")

        # Cadastro de ação
        with st.expander("➕ Cadastrar Ação", expanded=False):
            codigo_input = st.text_input("Código do Ativo (ex: PETR4)", key="cad_cod")
            preco_medio = st.text_input("Preço Médio (ex: 32,00)", key="cad_medio")
            preco_teto = st.text_input("Preço Teto (ex: 33,00)", key="cad_teto")
            if st.button("Salvar Ação", key="btn_salvar_acao"):
                codigo = normalizar_codigo(codigo_input)
                try:
                    pm = str_para_float(preco_medio)
                    pt = str_para_float(preco_teto)
                    tk = yf.Ticker(codigo)
                    hist = tk.history(period="1mo", interval="1d")
                    if hist.empty or hist['Close'].dropna().empty:
                        st.error("Código inválido ou sem pregão recente.")
                    else:
                        salvar_acao_google(sheet, codigo, pm, pt)
                        st.success(f"{codigo} salvo!")
                        st.experimental_rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")

        if ativos:
            # Editar ação
            with st.expander("✏️ Editar Ação", expanded=False):
                ativo_ed = st.selectbox("Selecione o Ativo", list(ativos.keys()), key="edicao_acao")
                novo_med = st.text_input("Novo Preço Médio", value=float_para_str(ativos[ativo_ed]["preco_medio"]), key="novo_med")
                novo_teto = st.text_input("Novo Preço Teto", value=float_para_str(ativos[ativo_ed]["preco_teto"]), key="novo_teto")
                if st.button("Atualizar Ação", key="btn_atualizar_acao"):
                    try:
                        pm = str_para_float(novo_med)
                        pt = str_para_float(novo_teto)
                        salvar_acao_google(sheet, ativo_ed, pm, pt)
                        st.success(f"{ativo_ed} atualizado!")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

            # Excluir ação
            with st.expander("🗑️ Excluir Ação", expanded=False):
                ativo_exc = st.selectbox("Selecione para Excluir", list(ativos.keys()), key="excluir_acao")
                if st.button("Remover", key="btn_remover_acao"):
                    excluir_acao_google(sheet, ativo_exc)
                    st.warning(f"{ativo_exc} removido!")
                    st.experimental_rerun()

    if not ativos:
        st.info("Nenhuma ação cadastrada. Adicione uma na barra lateral.")
        return

    # ------------------- Cards -------------------
    codigos_str = " ".join(ativos.keys())
    dados_acoes = yf.download(codigos_str, period="5d", interval="1d", progress=False, group_by='ticker')

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
                dados_ativo = dados_acoes.get(codigo)

            if dados_ativo is None or dados_ativo.empty or dados_ativo['Close'].dropna().empty:
                with cols[i % 5]:
                    st.warning(f"Sem dados para {codigo.replace('.SA','')} (final de semana/feriado?)")
                i += 1
                continue

            close_series = dados_ativo['Close'].dropna()
            preco_atual = float(close_series.iloc[-1])
            preco_anterior = float(close_series.iloc[-2]) if len(close_series) > 1 else preco_atual
            variacao = ((preco_atual - preco_anterior) / preco_anterior) * 100 if preco_anterior else 0
            mensagem, cor_borda = avaliar_alerta(preco_atual, info["preco_teto"])

            with cols[i % 5]:
                html_card = f"""
                <div style="border:7px solid {cor_borda}; border-radius:10px; 
                            padding:20px; margin-bottom:55px; height:250px; 
                            display:flex; flex-direction:column; justify-content:space-between;
                            box-shadow: 0 5px 8px 0 rgba(0,0,0,0.2);">
                    <h4 style="text-align:center; margin-top:-20px; margin-bottom:-2px;">{codigo.replace('.SA','')}</h4>
                    <div style="background-color:{cor_borda}; color:white; text-align:center; 
                                padding:5px; border-radius:5px; font-weight:bold;">
                        {mensagem}
                    </div>
                    <b>Preço Atual: R$ {float_para_str(preco_atual)}</b>
                    Preço Médio: R$ {float_para_str(info['preco_medio'])}
                    Preço Teto: R$ {float_para_str(info['preco_teto'])}</p>
                    <p>Variação D-1: <span style="color:{'green' if variacao >= 0 else 'red'}; font-weight:bold;">
                        {'▲' if variacao >= 0 else '▼'} {variacao:.2f}%
                    </span></p>  
                </div>
                """
                st.markdown(html_card, unsafe_allow_html=True)

            i += 1

        except Exception as e:
            with cols[i % 5]:
                st.error(f"Erro no card de {codigo.replace('.SA','')}: {e}")
            i += 1

# ------------------- Main -------------------
painel_acoes()

