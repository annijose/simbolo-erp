# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime
import libsql_client
import requests
from bs4 import BeautifulSoup
import os
from fpdf import FPDF
import unicodedata

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="S.I.M.B.O.L.O. - Gestión Logial", layout="wide", page_icon="🏛️")

# --- 2. LISTAS MAESTRAS Y CONSTANTES ---
CAT_INGRESO = ["Capitación Mensual", "Deuda Año Anterior", "Cuota Extraordinaria", "Derechos de Iniciación", "Derechos de Pasaje", "Derechos de Exaltación", "Donación / Otros"]
CAT_EGRESO = ["Aporte Gran Logia", "Gastos de Templo", "Servicios (Luz/Agua)", "Comisión Bancaria", "Mantenimiento", "Otros"]
MESES_ANNO = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
GRADOS = ["Aprendiz", "Compañero", "Maestro Mason", "Past Master"]
CARGOS = ["Ninguno", "Venerable Maestro", "1er Vigilante", "2do Vigilante", "Orador Fiscal", "Secretario", "Tesorero", "Hospitalario", "Experto", "Maestro de Ceremonias", "Guarda Templo", "Primer Diácono", "Segundo Diácono", "Económo", "Maestro de Banquetes"]

TAB_ING = "📥 Ingresos"
TAB_EGR = "📤 Egresos"
TAB_DIA = "📖 Diario"
TAB_REC = "🖨️ Recibos"
TAB_DAS = "📊 Dashboards"
TAB_ACT = "📜 Actas y Asistencia"
TAB_HOS = "❤️ Hospitalario"
TAB_USU = "👥 Usuarios"
TAB_CON = "⚙️ Config"
TAB_POR = "🏠 Mi Portal"
TAB_MRE = "📄 Mis Recibos"

# --- FUNCIÓN PARA QUITAR ACENTOS ---
def quitar_acentos(texto):
    if not texto: return ""
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('utf-8')

# --- 3. CONEXIÓN A TURSO ---
def get_client():
    url = st.secrets["TURSO_DATABASE_URL"]
    token = st.secrets["TURSO_AUTH_TOKEN"]
    return libsql_client.create_client_sync(url=url, auth_token=token)

@st.cache_resource
def init_db():
    client = get_client()
    try:
        client.execute('''CREATE TABLE IF NOT EXISTS movimientos 
                     (id TEXT PRIMARY KEY, fecha TEXT, origen_destino TEXT, tipo_operacion TEXT, 
                      categoria TEXT, detalle TEXT, referencia TEXT, monto_usd REAL, tasa_bcv REAL, monto_bs REAL)''')
        client.execute('''CREATE TABLE IF NOT EXISTS usuarios 
                     (username TEXT PRIMARY KEY, password TEXT, nombre_qh TEXT, grado TEXT, rol TEXT, perm_tesoreria INTEGER, perm_secretaria INTEGER, cargo_logia TEXT)''')
        client.execute('''CREATE TABLE IF NOT EXISTS actas 
                     (id_acta TEXT PRIMARY KEY, fecha TEXT, tipo_tenida TEXT, bosquejo TEXT, grado_tenida TEXT)''')
        client.execute('''CREATE TABLE IF NOT EXISTS asistencia 
                     (id_registro INTEGER PRIMARY KEY AUTOINCREMENT, id_acta TEXT, nombre_qh TEXT, asistio INTEGER)''')
        client.execute('''CREATE TABLE IF NOT EXISTS hospitalario 
                     (id_registro INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, detalle TEXT, monto_usd REAL, tasa_bcv REAL, monto_bs REAL)''')
        
        client.execute("INSERT OR IGNORE INTO usuarios (username, password, nombre_qh, grado, rol, perm_tesoreria, perm_secretaria, cargo_logia) VALUES ('admin', '113', 'ADMINISTRADOR GENERAL', 'Past Master', 'Administrador', 1, 1, 'Ninguno')")
        
        usr_anni = quitar_acentos("Annijose Goitia".replace(" ", "").lower())
        client.execute("INSERT OR IGNORE INTO usuarios (username, password, nombre_qh, grado, rol, perm_tesoreria, perm_secretaria, cargo_logia) VALUES (?, '113', 'Annijosé Goitia', 'Maestro Mason', 'Administrador', 1, 1, 'Tesorero')", (usr_anni,))
    finally:
        client.close()

init_db()

# --- 4. FUNCIONES DE APOYO ---
def logout():
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.rerun()

def leer_datos(tabla="movimientos"):
    client = get_client()
    try:
        res = client.execute(f"SELECT * FROM {tabla}")
        return pd.DataFrame([list(r) for r in res.rows], columns=res.columns)
    finally:
        client.close()

def obtener_miembros():
    client = get_client()
    try:
        res = client.execute("SELECT nombre_qh, grado FROM usuarios")
        df = pd.DataFrame([list(r) for r in res.rows], columns=res.columns)
    finally:
        client.close()
    lista_nombres = df['nombre_qh'].tolist()
    dict_grados = {row['nombre_qh']: row['grado'] for _, row in df.iterrows()}
    if "CABALLERO PROFANO" not in lista_nombres:
        lista_nombres.append("CABALLERO PROFANO")
        dict_grados["CABALLERO PROFANO"] = "Profano"
    return sorted(list(set(lista_nombres))), dict_grados

@st.cache_data(ttl=3600)
def obtener_tasa_bcv():
    try:
        url = "https://www.bcv.org.ve/"
        response = requests.get(url, verify=False, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        tasa_str = soup.find(id="dolar").find("strong").text.strip()
        return round(float(tasa_str.replace(',', '.')), 2)
    except: return 45.00

if 'tasa_actual' not in st.session_state:
    st.session_state.tasa_actual = obtener_tasa_bcv()

def texto_seguro(texto):
    if not texto: return ""
    return str(texto).encode('latin-1', 'replace').decode('latin-1')

def formatear_miles(df):
    columnas_monto = ['monto_usd', 'tasa_bcv', 'monto_bs']
    formato = {}
    for col in columnas_monto:
        if col in df.columns:
            formato[col] = lambda x: f"{x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    return formato

class FormatoPDF(FPDF):
    def header(self):
        if os.path.exists("logo.png"): self.image("logo.png", 10, 8, 25)
        self.set_y(10)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 5, texto_seguro('Al G.·. D.·. G.·. A.·. D.·. U.·.'), ln=True, align='C')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 6, texto_seguro('RESPETABLE LOGIA SIMBOLO No 113'), ln=True, align='C')
        self.set_font('Arial', 'I', 8)
        self.cell(0, 5, texto_seguro('R.·. E.·. A.·. A.·.'), ln=True, align='C')
        self.ln(10)

def generar_recibo_multiple(datos_master, items_carrito, grado_qh=""):
    pdf = FormatoPDF(); pdf.add_page()
    pdf.set_font('Arial', 'B', 12); pdf.cell(0, 10, texto_seguro(f"S.I.M.B.O.L.O. - RECIBO DE PAGO - {datos_master['qh'].upper()}"), ln=True, align='C')
    pdf.set_font('Arial', 'B', 10); pdf.cell(0, 5, f"N° LSN113-{datos_master['id']}", ln=True, align='R'); pdf.ln(5)
    nombre_completo = f"{grado_qh} {datos_master['qh']}" if grado_qh != "Profano" else datos_master['qh']
    pdf.cell(40, 8, "Recibido de:", 1); pdf.set_font('Arial', '', 10); pdf.cell(0, 8, texto_seguro(f" {nombre_completo}"), 1, 1)
    pdf.set_font('Arial', 'B', 10); pdf.cell(40, 8, "Fecha / Ref:", 1); pdf.set_font('Arial', '', 10); pdf.cell(0, 8, texto_seguro(f"{datos_master['fecha']} / {datos_master['ref']}"), 1, 1); pdf.ln(5)
    
    es_hist = any("HISTÓRICA" in str(item.get('ref', '')) for item in items_carrito)
    if es_hist:
        pdf.set_text_color(180, 0, 0); pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, texto_seguro("NOTA: ESTE ES UN REGISTRO HISTÓRICO DE MIGRACIÓN."), ln=True); pdf.set_text_color(0, 0, 0); pdf.ln(2)

    pdf.set_font('Arial', 'B', 9); pdf.set_fill_color(230, 230, 230); pdf.cell(80, 7, "Concepto", 1, 0, 'C', True); pdf.cell(50, 7, "Monto USD", 1, 0, 'C', True); pdf.cell(50, 7, "Monto Bs.", 1, 1, 'C', True)
    pdf.set_font('Arial', '', 9)
    for item in items_carrito:
        pdf.cell(80, 7, texto_seguro(f"{item['categoria']}: {item['detalle']}"), 1); pdf.cell(50, 7, f"{item['monto_usd']:,.2f} $", 1, 0, 'R'); pdf.cell(50, 7, f"{item['monto_bs']:,.2f} Bs.", 1, 1, 'R')
    pdf.set_font('Arial', 'B', 10); pdf.cell(80, 8, "TOTAL", 1); pdf.cell(50, 8, f"{datos_master['monto_usd']:,.2f} $", 1, 0, 'R'); pdf.cell(50, 8, f"{datos_master['monto_bs']:,.2f} Bs.", 1, 1, 'R')
    pdf.ln(35); pdf.set_font('Arial', 'B', 10); pdf.cell(0, 5, texto_seguro("Annijosé Goitia León"), ln=True, align='R'); pdf.set_font('Arial', 'I', 9); pdf.cell(0, 5, "Tesorero", ln=True, align='R')
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- 5. LÓGICA DE ACCESO ---
if "logged_in" not in st.session_state:
    st.title("🏛️ S.I.M.B.O.L.O. - Portal Logial")
    u = st.text_input("Usuario"); p = st.text_input("Clave", type="password")
    if st.button("Ingresar", type="primary"):
        client = get_client()
        try:
            res = client.execute("SELECT username, password, nombre_qh, grado, rol, perm_tesoreria, perm_secretaria, cargo_logia FROM usuarios WHERE username=? AND password=?", (u, p))
            if res.rows:
                row = res.rows[0]; st.session_state["logged_in"] = True
                p_rol = row[4]; p_cargo = row[7]
                p_teso = 1 if p_rol == 'Administrador' or p_cargo == 'Tesorero' else row[5]
                p_sec = 1 if p_rol == 'Administrador' or p_cargo == 'Secretario' else row[6]
                st.session_state["u_info"] = {"u": row[0], "nombre": row[2], "grado": row[3], "rol": p_rol, "teso": p_teso, "sec": p_sec, "cargo": p_cargo}
                st.rerun()
            else: st.error("Acceso denegado")
        finally: client.close()
else:
    info = st.session_state["u_info"]; lista_qh, dict_grados = obtener_miembros()
    is_hosp = info['cargo'] == 'Hospitalario' or info['rol'] == 'Administrador'
    tratamiento = "V.·.H.·." if info['grado'] in ['Maestro Mason', 'Past Master'] else "Q.·.H.·."
    
    with st.sidebar:
        st.title("🏛️ S.I.M.B.O.L.O.")
        st.write(f"{tratamiento} **{info['nombre']}**")
        if st.button("🚪 Cerrar Sesión", type="primary"): logout()
        if info['teso']:
            st.divider(); st.header("📊 Resumen de Caja")
            df_actual = leer_datos()
            b_bs = df_actual[~df_actual['referencia'].str.contains("EFECTIVO", case=False, na=False)]['monto_bs'].sum()
            c_usd = df_actual[df_actual['referencia'].str.contains("EFECTIVO", case=False, na=False)]['monto_usd'].sum()
            st.metric("🏦 Banco Actual", f"{b_bs:,.2f} Bs.".replace(',', 'X').replace('.', ',').replace('X', '.'))
            st.metric("💵 Caja Actual", f"{c_usd:,.2f} $".replace(',', 'X').replace('.', ',').replace('X', '.'))

    m_tabs = []
    if info['rol'] != 'Administrador': m_tabs += [TAB_POR, TAB_MRE]
    if info['teso']: m_tabs += [TAB_ING, TAB_EGR, TAB_DIA, TAB_REC, TAB_DAS]
    if info['sec']: m_tabs += [TAB_ACT]
    if is_hosp: m_tabs += [TAB_HOS]
    if info['rol'] == 'Administrador': m_tabs += [TAB_USU, TAB_CON]
    tabs = st.tabs(m_tabs)

    # --- MÓDULO INGRESOS ---
    if TAB_ING in m_tabs:
        with tabs[m_tabs.index(TAB_ING)]:
            if 'carrito' not in st.session_state: st.session_state.carrito = []
            if 'u_recibo' not in st.session_state: st.session_state.u_recibo = None
            if 'f_key' not in st.session_state: st.session_state.f_key = 0
            st.subheader("📝 Punto de Venta")
            c_g1, c_g2, c_g3, c_g4 = st.columns([2, 1.5, 1.5, 1])
            qh_in = c_g1.selectbox("QQ.·.HH.·.", lista_qh, key=f"qh_{st.session_state.f_key}")
            fecha_p = c_g2.date_input("Fecha Pago", datetime.now(), key=f"fp_{st.session_state.f_key}")
            met_in = c_g3.radio("Método", ["Transferencia", "Efectivo USD"], horizontal=True, key=f"mt_{st.session_state.f_key}")
            com_ajuste = st.checkbox("¿Aplica Comisión 1.5%?", value=True) if met_in == "Transferencia" else False
            es_hist = c_g3.checkbox("Registro Histórico ($0 en caja)", key=f"hist_{st.session_state.f_key}")
            ts_in = c_g4.number_input("Tasa BCV", value=st.session_state.tasa_actual, key=f"ts_{st.session_state.f_key}", format="%.4f")
            with st.expander("➕ Añadir Concepto", expanded=True):
                c_i1, c_i2, c_i3 = st.columns([3,2,1])
                cat_t = c_i1.selectbox("Concepto", CAT_INGRESO, key=f"cat_{st.session_state.f_key}")
                if cat_t == "Capitación Mensual":
                    m_list = c_i1.multiselect("Meses", MESES_ANNO, key=f"meses_{st.session_state.f_key}")
                    if len(m_list) == 12 and met_in == "Efectivo USD":
                        d_t = "AÑO COMPLETO (PRONTO PAGO EN EFECTIVO)"; m_t = 150.0; st.success("🎉 ¡PRONTO PAGO!")
                    else: d_t = ", ".join(m_list); m_t = (len(m_list) * 15.0)
                else: d_t = c_i1.text_input("Descripción", key=f"desc_{st.session_state.f_key}"); m_t = c_i1.number_input("Monto USD", value=15.0, key=f"m_{st.session_state.f_key}")
                ref_t = c_i2.text_input("Ref. Pago", key=f"ref_{st.session_state.f_key}")
                if es_hist: m_t_f, m_b_f, r_f = 0.0, 0.0, "MIGRACIÓN HISTÓRICA"
                else: m_t_f, m_b_f, r_f = m_t, round(m_t * ts_in, 2), "EFECTIVO" if met_in == "Efectivo USD" else ref_t
                if c_i3.button("➕ Añadir"):
                    st.session_state.carrito.append({"id_t": datetime.now().strftime('%f'), "categoria": cat_t, "detalle": d_t, "monto_usd": m_t_f, "monto_bs": m_b_f, "ref": r_f})
                    st.rerun()
            if st.session_state.carrito:
                for i, it in enumerate(st.session_state.carrito):
                    cols = st.columns([4,1,1,0.5]); cols[0].write(f"{it['categoria']}: {it['detalle']}"); cols[1].write(f"{it['monto_usd']}$"); cols[2].write(f"{it['monto_bs']}Bs")
                    if cols[3].button("🗑️", key=f"del_{it['id_t']}"): st.session_state.carrito.pop(i); st.rerun()
                if st.button("🚀 Procesar e Imprimir", type="primary", use_container_width=True):
                    id_m = datetime.now().strftime('%y%m%d%H%M%S'); client = get_client()
                    try:
                        for idx, it in enumerate(st.session_state.carrito):
                            client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", (f"{id_m}-{idx}", str(fecha_p), qh_in, "INGRESO", it['categoria'], it['detalle'], it['ref'], it['monto_usd'], ts_in, it['monto_bs']))
                            if met_in == "Transferencia" and not es_hist and com_ajuste:
                                c_bs = round(it['monto_bs'] * 0.015, 2); c_usd = round(c_bs / ts_in, 2)
                                client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", (f"COM-{id_m}-{idx}", str(fecha_p), 'BBVA Provincial', 'EGRESO', 'Comisión Bancaria', f'Comisión 1.5% - Ref In: {it["ref"]}', 'COMIS. CRI OB REC', -abs(c_usd), ts_in, -abs(c_bs)))
                    finally: client.close()
                    pdf = generar_recibo_multiple({'id': id_m, 'fecha': str(fecha_p), 'qh': qh_in, 'monto_usd': sum(x['monto_usd'] for x in st.session_state.carrito), 'monto_bs': sum(x['monto_bs'] for x in st.session_state.carrito), 'ref': st.session_state.carrito[0]['ref']}, st.session_state.carrito, dict_grados.get(qh_in, ""))
                    st.session_state.u_recibo = {"bytes": pdf, "n": f"Recibo_{id_m}.pdf"}; st.session_state.carrito = []; st.session_state.f_key += 1; st.rerun()
            if st.session_state.u_recibo:
                st.download_button("📥 Descargar PDF", st.session_state.u_recibo['bytes'], st.session_state.u_recibo['n'], mime="application/pdf", use_container_width=True)
                if st.button("🔄 Nuevo Cobro"): st.session_state.u_recibo = None; st.rerun()

    # --- MÓDULO EGRESOS ---
    if TAB_EGR in m_tabs:
        with tabs[m_tabs.index(TAB_EGR)]:
            if 'eg_key' not in st.session_state: st.session_state.eg_key = 0
            st.subheader("📤 Registrar Egreso")
            c_e1, c_e2 = st.columns(2)
            f_e = c_e1.date_input("Fecha", datetime.now(), key=f"ef_{st.session_state.eg_key}")
            ben_e = c_e1.text_input("Beneficiario", key=f"eb_{st.session_state.eg_key}")
            cat_e = c_e1.selectbox("Concepto", CAT_EGRESO, key=f"ec_{st.session_state.eg_key}")
            met_e = c_e1.radio("Origen:", ["Banco (Bs)", "Caja Chica (USD)"], horizontal=True, key=f"em_{st.session_state.eg_key}")
            t_e = c_e2.number_input("Tasa", value=st.session_state.tasa_actual, key=f"et_{st.session_state.eg_key}", format="%.4f")
            if met_e == "Caja Chica (USD)":
                m_u_e = c_e2.number_input("USD", key=f"egu_{st.session_state.eg_key}"); m_b_e = round(m_u_e * t_e, 2); r_e = "EFECTIVO"
            else:
                m_b_e = c_e2.number_input("Bs", key=f"ebs_{st.session_state.eg_key}"); m_u_e = round(m_b_e / t_e, 2); r_e = c_e2.text_input("Referencia", key=f"er_{st.session_state.eg_key}")
            nota_e = c_e2.text_input("Nota", key=f"en_{st.session_state.eg_key}")
            if st.button("Registrar Salida", type="primary"):
                id_e = f"EG-{datetime.now().strftime('%y%m%d%H%M%S')}"; client = get_client()
                try: client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", (id_e, str(f_e), ben_e, "EGRESO", cat_e, nota_e, r_e, -abs(m_u_e), t_e, -abs(m_b_e)))
                finally: client.close(); st.session_state.eg_key += 1; st.rerun()

    # --- MÓDULO DIARIO ---
    if TAB_DIA in m_tabs:
        with tabs[m_tabs.index(TAB_DIA)]:
            st.subheader("📖 Libro Diario"); df = leer_datos()
            c_d1, c_d2 = st.columns(2)
            m_s = c_d1.selectbox("Mes", MESES_ANNO, index=datetime.now().month-1); a_s = c_d2.selectbox("Año", [2025, 2026], index=1)
            if not df.empty:
                df['fecha_dt'] = pd.to_datetime(df['fecha'], errors='coerce')
                df_m = df[(df['fecha_dt'].dt.month == MESES_ANNO.index(m_s)+1) & (df['fecha_dt'].dt.year == a_s)]
                st.dataframe(df_m.drop(columns=['fecha_dt']).style.format(formatear_miles(df_m)), use_container_width=True)

    # --- MÓDULO DASHBOARDS (REDISEÑADO) ---
    if TAB_DAS in m_tabs:
        with tabs[m_tabs.index(TAB_DAS)]:
            st.title("📊 Auditoría y Balances")
            df_m = leer_datos()
            
            st.subheader("🗓️ Reporte de Balance Trimestral")
            c_b1, c_b2 = st.columns(2)
            trim_sel = c_b1.selectbox("Seleccione Trimestre", ["1er Trimestre (Ene-Mar)", "2do Trimestre (Abr-Jun)", "3er Trimestre (Jul-Sep)", "4to Trimestre (Oct-Dic)"])
            año_sel = c_b2.selectbox("Año Auditoría", [2025, 2026], index=1)
            
            meses_trim = {
                "1er Trimestre (Ene-Mar)": [1, 2, 3],
                "2do Trimestre (Abr-Jun)": [4, 5, 6],
                "3er Trimestre (Jul-Sep)": [7, 8, 9],
                "4to Trimestre (Oct-Dic)": [10, 11, 12]
            }
            
            if not df_m.empty:
                df_m['fecha_dt'] = pd.to_datetime(df_m['fecha'], errors='coerce')
                df_trim = df_m[(df_m['fecha_dt'].dt.month.isin(meses_trim[trim_sel])) & (df_m['fecha_dt'].dt.year == año_sel)]
                
                # CÁLCULO SEPARADO PARA CONCILIACIÓN
                # Solo Banco (Lo que no es EFECTIVO)
                df_banco = df_trim[~df_trim['referencia'].str.contains("EFECTIVO", case=False, na=False)]
                t_ing_bs = df_banco[df_banco['tipo_operacion'] == 'INGRESO']['monto_bs'].sum()
                t_egr_bs = df_banco[df_banco['tipo_operacion'] == 'EGRESO']['monto_bs'].sum()
                saldo_banco_trim = t_ing_bs + t_egr_bs
                
                # Solo Caja Chica (Lo que es EFECTIVO)
                df_caja = df_trim[df_trim['referencia'].str.contains("EFECTIVO", case=False, na=False)]
                t_ing_usd = df_caja[df_caja['tipo_operacion'] == 'INGRESO']['monto_usd'].sum()
                t_egr_usd = df_caja[df_caja['tipo_operacion'] == 'EGRESO']['monto_usd'].sum()
                saldo_caja_trim = t_ing_usd + t_egr_usd

                col_trim1, col_trim2, col_trim3 = st.columns(3)
                col_trim1.metric("Movimiento Banco (Bs)", f"{saldo_banco_trim:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
                col_trim2.metric("Movimiento Caja (USD)", f"{saldo_caja_trim:,.2f} $")
                col_trim3.metric("Equiv. USD Total (Tasa Actual)", f"{(saldo_banco_trim / st.session_state.tasa_actual + saldo_caja_trim):,.2f} $")
                
                st.write("**Detalle Multimoneda de Movimientos**")
                # Añadimos columna de referencia a USD para el reporte
                df_trim_view = df_trim.copy()
                df_trim_view['equiv_usd_al_dia'] = df_trim_view.apply(lambda x: x['monto_usd'] if x['monto_usd'] != 0 else x['monto_bs'] / x['tasa_bcv'], axis=1)
                
                st.dataframe(df_trim_view.drop(columns=['fecha_dt']).style.format(formatear_miles(df_trim_view)), use_container_width=True)
                
                csv = df_trim_view.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(f"📥 Exportar Balance a Excel", data=csv, file_name=f"Balance_{trim_sel}.csv")

    # --- MÓDULO CONFIGURACIÓN (RESTAURADO) ---
    if TAB_CON in m_tabs:
        with tabs[m_tabs.index(TAB_CON)]:
            st.subheader("⚙️ Configuración")
            st.write("**🚨 Anulación de Movimientos**")
            df_m = leer_datos()
            if not df_m.empty:
                ops = {}
                for _, r in df_m.sort_values(by='fecha', ascending=False).iterrows():
                    if not str(r['id']).startswith("COM-"):
                        lbl = f"QH: {r['origen_destino']} | Monto: {r['monto_bs']:,.2f} Bs | Fecha: {r['fecha']} | ID: {r['id']}"; ops[lbl] = r['id']
                id_anul = st.selectbox("Seleccione para ANULAR", list(ops.keys()))
                if st.button("❌ ANULAR SELECCIONADO", type="primary"):
                    client = get_client(); rid = ops[id_anul]
                    try: 
                        client.execute("DELETE FROM movimientos WHERE id=?", (rid,))
                        client.execute("DELETE FROM movimientos WHERE id LIKE ?", (f"COM-{rid}%",))
                        st.success("Anulado."); st.rerun()
                    finally: client.close()
            st.divider(); st.error("🚨 ZONA DE PELIGRO")
            if st.checkbox("Confirmo borrar TODO"):
                if st.button("VACIAR BD"):
                    client = get_client()
                    try: 
                        for t in ["movimientos", "actas", "asistencia", "hospitalario"]: client.execute(f"DELETE FROM {t}")
                    finally: client.close(); logout()
