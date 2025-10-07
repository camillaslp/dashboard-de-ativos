# main.py
import streamlit as st
st.set_page_config(layout="wide")
import yfinance as yf
import json
import warnings
from google.oauth2.service_account import Credentials
import gspread
import datetime
import pytz

warnings.filterwarnings("ignore", category=FutureWarning)

# ------------------- Configurações -------------------
SHEET_NAME = "Acoes"      # aba com cabeçalho: codigo, preco_medio, preco_teto
COTACOES_TAB = "Cotacoes" # aba para guardar última cotação, preco_anterior, timestamp

# ------------------- Conectar Google Sheets -------------------
try:
    creds_dict = json.loads(st.secrets["GOOGLE_CREDS"])
except KeyError:
    print("Chave 'GOOGLE_CREDS' não encontrada em st.secrets. Configure em Deploy > Secrets.")
    st.stop()
except json.JSONDecodeError as e:
    print(f"Erro ao decodificar JSON das credenciais: {e}")
    st.stop()

scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

try:
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
except Exception as e:
    print(f"Erro ao autenticar no Google Sheets: {e}")
    st.stop()

# abrir spreadsheet e aba principal (Acoes)
try:
    spreadsheet = client.open(SHEET_NAME)
    # tenta abrir aba chamada exatamente "Acoes", se não existir usa sheet1
    try:
        sheet_acoes = spreadsheet.worksheet("Acoes")
    except gspread.exceptions.WorksheetNotFound:
        sheet_acoes = spreadsheet.sheet1
except gspread.exceptions.SpreadsheetNotFound:
    print(f"Planilha '{SHEET_NAME}' não encontrada. Verifique nome e compartilhamento com o Service Account.")
    st.stop()
except Exception as e:
    print(f"Erro ao abrir planilha: {e}")
    st.stop()

# ------------------- Utilitários -------------------
def normalizar_codigo(codigo):
    c = str(codigo).strip().upper()
    if c and not c.endswith(".SA"):
        c += ".SA"
    return c

def str_para_float(valor_str):
    """
    Converte entrada como "32,50" ou "3.200,00" ou "32.50" ou números para float 32.5
    """
    if valor_str is None or valor_str == "":
        return 0.0
    if isinstance(valor_str, (int, float)):
        return float(valor_str)
    v = str(valor_str).strip()
    v = v.replace("\xa0", "").replace(" ", "")
    # Se tem '.' e ',' -> assume '.' separador de milhares -> remove pontos -> trocar vírgula por ponto
    if "." in v and "," in v:
        v = v.replace(".", "").replace(",", ".")
    else:
        v = v.replace(",", ".")
    try:
        return float(v)
    except:
        return 0.0

def float_para_str(valor_float):
    """Formata float para string '32,50' (vírgula) ou 'N/D' se None"""
    try:
        if valor_float is None:
            return "N/D"
        return f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "N/D"

def ensure_cotacoes_tab(spreadsheet):
    """Garante que a aba Cotacoes exista com cabeçalho (codigo, ultima_cotacao, preco_anterior, data_hora)"""
    try:
        w = spreadsheet.worksheet(COTACOES_TAB)
    except gspread.exceptions.WorksheetNotFound:
        w = spreadsheet.add_worksheet(title=COTACOES_TAB, rows="500", cols="4")
        w.append_row(["codigo", "ultima_cotacao", "preco_anterior", "data_hora"])
    # garantir que header tenha 4 colunas (caso exista versão antiga)
    header = w.row_values(1)
    if len(header) < 4:
        # reescreve header completo
        w.update("A1:D1", [["codigo", "ultima_cotacao", "preco_anterior", "data_hora"]])
    return w

# ------------------- Função de alerta (definida antes do uso) -------------------
def avaliar_alerta(preco_atual, preco_teto):
    """
    Retorna (mensagem, cor).
    Se preco_atual for None -> retorna 'N/D' e cinza.
    """
    if preco_atual is None:
        return "N/D", "gray"
    try:
        if preco_teto is None:
            return "Manter Posição", "gray"
        if preco_atual < preco_teto:
            return "🟢 Oportunidade", "green"
        elif preco_atual > preco_teto * 1.1:
            return "🔴 Acima do Teto", "red"
        else:
            return "Manter Posição", "gray"
    except Exception:
        return "Manter Posição", "gray"

# ------------------- Operações com Ações (aba Acoes) -------------------
def carregar_acoes_google():
    """Lê a aba 'Acoes' e retorna dict { 'TICKER.SA': {preco_medio: float, preco_teto: float} }"""
    try:
        registros = sheet_acoes.get_all_records()
    except Exception as e:
        print(f"Erro ao ler aba Acoes: {e}")
        return {}
    ativos = {}
    for r in registros:
        codigo = normalizar_codigo(r.get("codigo", ""))
        if not codigo:
            continue
        pm = str_para_float(r.get("preco_medio", 0))
        pt = str_para_float(r.get("preco_teto", 0))
        ativos[codigo] = {"preco_medio": pm, "preco_teto": pt}
    return ativos

def salvar_acao_google(codigo, preco_medio, preco_teto):
    """Atualiza ou adiciona ação no Google Sheets (salva números)"""
    codigo = normalizar_codigo(codigo)
    try:
        registros = sheet_acoes.get_all_records()
    except Exception as e:
        print(f"Erro ao ler a planilha para salvar: {e}")
        return
    encontrado = False
    for i, r in enumerate(registros):
        if normalizar_codigo(r.get("codigo","")) == codigo:
            try:
                sheet_acoes.update(f"B{i+2}", float(preco_medio))
                sheet_acoes.update(f"C{i+2}", float(preco_teto))
            except Exception as e:
                print(f"Erro ao atualizar planilha: {e}")
            encontrado = True
            break
    if not encontrado:
        try:
            sheet_acoes.append_row([codigo, float(preco_medio), float(preco_teto)])
        except Exception as e:
            print(f"Erro ao adicionar linha: {e}")

def excluir_acao_google(codigo):
    codigo = normalizar_codigo(codigo)
    try:
        registros = sheet_acoes.get_all_records()
    except Exception as e:
        print(f"Erro ao ler a planilha para exclusão: {e}")
        return
    for i, r in enumerate(registros):
        if normalizar_codigo(r.get("codigo","")) == codigo:
            try:
                sheet_acoes.delete_row(i+2)
            except Exception as e:
                print(f"Erro ao deletar linha: {e}")
            break

# ------------------- Operações com Cotacoes (aba Cotacoes) -------------------
def carregar_cotacoes_do_sheet():
    """
    Retorna dict {codigo: {'preco_atual': float, 'preco_anterior': float or None, 'data_hora': str}}
    """
    cotacoes = {}
    w = ensure_cotacoes_tab(spreadsheet)
    try:
        regs = w.get_all_records()
    except Exception:
        return {}
    for r in regs:
        codigo = normalizar_codigo(r.get("codigo",""))
        if not codigo:
            continue
        ultima = r.get("ultima_cotacao", "")
        anterior = r.get("preco_anterior", "")
        ts = r.get("data_hora", "")
        try:
            pa = str_para_float(ultima)
        except:
            pa = None
        try:
            pan = str_para_float(anterior)
        except:
            pan = None
        cotacoes[codigo] = {"preco_atual": pa, "preco_anterior": pan, "data_hora": ts}
    return cotacoes

def atualizar_cotacao_no_sheet(codigo, preco_atual, preco_anterior=None):
    """
    Insere/atualiza a cotacao e timestamp na aba Cotacoes.
    Salva os valores como números (floats) e timestamp string.
    """
    codigo = normalizar_codigo(codigo)
    w = ensure_cotacoes_tab(spreadsheet)
    try:
        regs = w.get_all_records()
    except Exception as e:
        print(f"Erro ao acessar aba Cotacoes: {e}")
        return
    codigos = [normalizar_codigo(r.get("codigo","")) for r in regs]
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if codigo in codigos:
        linha = codigos.index(codigo) + 2
        try:
            # salva número (float) em B e C
            w.update(f"B{linha}", preco_atual)
            w.update(f"C{linha}", preco_anterior if preco_anterior is not None else "")
            w.update(f"D{linha}", ts)
        except Exception as e:
            print(f"Erro ao atualizar cotacao na sheet: {e}")
    else:
        try:
            w.append_row([codigo, preco_atual, preco_anterior if preco_anterior is not None else "", ts])
        except Exception as e:
            print(f"Erro ao inserir cotacao na sheet: {e}")

# ------------------- Buscar cotações com cache/fallback -------------------
def buscar_cotacoes_com_cache(codigos):
    resultados = {}
    timezone_br = pytz.timezone("America/Sao_Paulo")

    for codigo in codigos:
        try:
            tk = yf.Ticker(codigo)

            # tenta 1 mês primeiro
            hist = tk.history(period="1mo", interval="1d")
            close = hist["Close"].dropna()

            # fallback: se só tiver 1 fechamento, busca 2 meses
            if len(close) < 2:
                hist2 = tk.history(period="2mo", interval="1d")
                close = hist2["Close"].dropna()

            if len(close) == 0:
                raise Exception("Histórico vazio.")
            elif len(close) == 1:
                preco_atual = float(close.iloc[-1])
                preco_anterior = None
                variacao = None
            else:
                preco_atual = float(close.iloc[-1])
                preco_anterior = float(close.iloc[-2])
                variacao = ((preco_atual - preco_anterior) / preco_anterior) * 100 if preco_anterior else None

            # atualiza cache no sheet (se houver)
            atualizar_cotacao_no_sheet(codigo, preco_atual, preco_anterior)

            # salva resultado formatado
            resultados[codigo] = {
                "preco_atual": preco_atual,
                "preco_anterior": preco_anterior,
                "variacao": variacao,
                "status": "OK"
            }

        except Exception as e:
            print(f"Erro ao buscar {codigo}: {e}")
            resultados[codigo] = {
                "preco_atual": None,
                "preco_anterior": None,
                "variacao": None,
                "status": f"Erro: {e}"
            }

    return resultados

# ------------------- Painel (UI) -------------------
def painel_acoes():
    st.title("📊 Dashboard de Ações")

    # carregar ativos
    ativos = carregar_acoes_google()

    # sidebar: gerenciar
    with st.sidebar:
        st.header("⚙️ Gerenciar Ativos")

        # cadastrar
        with st.expander("➕ Cadastrar Ação", expanded=False):
            codigo_input = st.text_input("Código do Ativo (ex: PETR4)", key="cad_cod")
            preco_medio = st.text_input("Preço Médio (ex: 32,00)", key="cad_medio")
            preco_teto = st.text_input("Preço Teto (ex: 33,00)", key="cad_teto")
            if st.button("Salvar Ação", key="btn_salvar_acao"):
                codigo = normalizar_codigo(codigo_input)
                pm = str_para_float(preco_medio)
                pt = str_para_float(preco_teto)
                if not codigo:
                    print("Código inválido.")
                else:
                    try:
                        tk = yf.Ticker(codigo)
                        hist = tk.history(period="1mo", interval="1d")
                        if hist is None or hist.empty or hist["Close"].dropna().empty:
                            print("Código inválido ou sem pregão recente.")
                        else:
                            salvar_acao_google(codigo, pm, pt)
                            st.success(f"{codigo} salvo!")
                    except Exception as e:
                        print(f"Erro ao validar código: {e}")

        # editar/excluir
        if ativos:
            with st.expander("✏️ Editar Ação", expanded=False):
                ativo_ed = st.selectbox("Selecione o Ativo", list(ativos.keys()), key="edicao_acao")
                novo_med = st.text_input("Novo Preço Médio", value=float_para_str(ativos[ativo_ed]["preco_medio"]), key="novo_med")
                novo_teto = st.text_input("Novo Preço Teto", value=float_para_str(ativos[ativo_ed]["preco_teto"]), key="novo_teto")
                if st.button("Atualizar Ação", key="btn_atualizar_acao"):
                    pm = str_para_float(novo_med)
                    pt = str_para_float(novo_teto)
                    salvar_acao_google(ativo_ed, pm, pt)
                    st.success(f"{ativo_ed} atualizado!")

            with st.expander("🗑️ Excluir Ação", expanded=False):
                ativo_exc = st.selectbox("Selecione para Excluir", list(ativos.keys()), key="excluir_acao")
                if st.button("Remover", key="btn_remover_acao"):
                    excluir_acao_google(ativo_exc)
                    st.warning(f"{ativo_exc} removido!")

    if not ativos:
        st.info("Nenhuma ação cadastrada. Adicione na barra lateral.")
        return

    # Buscar cotações (com cache)
    cotacoes = buscar_cotacoes_com_cache(ativos)

    # Montar cards (5 colunas)
    cols = st.columns(5)
    i = 0
    for codigo, info in ativos.items():
        try:
            cot = cotacoes.get(codigo, {})
            preco_atual = cot.get("preco_atual")
            variacao = cot.get("variacao")
            preco_medio = info["preco_medio"]
            preco_teto = info["preco_teto"]

            texto_preco_atual = float_para_str(preco_atual) if preco_atual is not None else "N/D"
            texto_pm = float_para_str(preco_medio)
            texto_pt = float_para_str(preco_teto)
            mensagem, cor_borda = avaliar_alerta(preco_atual, preco_teto)

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
                    <b style="text-align:center;">Preço Atual: R$ {texto_preco_atual}</b>
                    <b style="text-align:center;">Preço Médio: R$ {texto_pm}</b>
                    <p style="text-align:center;"><b>Preço Teto: R$ {texto_pt}</b></p>
                    <p style="text-align:center;">Variação D-1: <span style="color:{'green' if (variacao is not None and variacao >= 0) else 'red'}; font-weight:bold;">
                        {'▲' if (variacao is not None and variacao >= 0) else '▼'} {f'{variacao:.2f}%' if variacao is not None else 'N/D'}
                    </span></p>
                    </div>
                """
                st.markdown(html_card, unsafe_allow_html=True)

            i += 1

        except Exception as e:
            with cols[i % 5]:
                print(f"Erro no card de {codigo.replace('.SA','')}: {e}")
            i += 1

# ------------------- Execução -------------------
if __name__ == "__main__":
    painel_acoes()


