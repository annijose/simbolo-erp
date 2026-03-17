# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime
import libsql_client
import requests
from bs4 import BeautifulSoup
import os
from fpdf import FPDF

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="S.I.M.B.O.L.O. - Gestión Logial", layout="wide", page_icon="🏛️")

# --- 2. LISTAS MAESTRAS Y CONSTANTES ---
CAT_INGRESO = ["Capitación Mensual", "Deuda Año Anterior", "Cuota Extraordinaria", "Derechos de Iniciación", "Derechos de Aumento de Salario", "Derechos de Exaltación", "Donación / Otros"]
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

# --- 3. CONEXIÓN A TURSO (LA NUBE) ---
def get_client():
    url = st.secrets["TURSO_DATABASE_URL"]
    token = st.secrets["TURSO_AUTH_TOKEN"]
    return libsql_client.create_client_sync(url=url, auth_token=token)

def init_db():
    client = get_client()
    try:
        client.execute('''CREATE TABLE IF NOT EXISTS movimientos 
                     (id TEXT PRIMARY KEY, fecha TEXT, origen_destino TEXT, tipo_operacion TEXT, 
                      categoria TEXT, detalle TEXT, referencia TEXT, monto_usd REAL, tasa_bcv REAL, monto_bs REAL)''')
        client.execute('''CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)''')
        client.execute('''CREATE TABLE IF NOT EXISTS usuarios 
                     (username TEXT PRIMARY KEY, password TEXT, nombre_qh TEXT, grado TEXT, rol TEXT, perm_tesoreria INTEGER, perm_secretaria INTEGER, cargo_logia TEXT)''')
        client.execute('''CREATE TABLE IF NOT EXISTS actas 
                     (id_acta TEXT PRIMARY KEY, fecha TEXT, tipo_tenida TEXT, bosquejo TEXT, grado_tenida TEXT)''')
        client.execute('''CREATE TABLE IF NOT EXISTS asistencia 
                     (id_registro INTEGER PRIMARY KEY AUTOINCREMENT, id_acta TEXT, nombre_qh TEXT, asistio INTEGER)''')
        client.execute('''CREATE TABLE IF NOT EXISTS hospitalario 
                     (id_registro INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, detalle TEXT, monto_usd REAL, tasa_bcv REAL, monto_bs REAL)''')
        
        # Usuario Admin base
        client.execute("INSERT OR IGNORE INTO usuarios (username, password, nombre_qh, grado, rol, perm_tesoreria, perm_secretaria, cargo_logia) VALUES ('admin', '113', 'ANNIJOSÉ GOITIA', 'Maestro Mason', 'Administrador', 1, 1, 'Tesorero')")
        
        # Forzar la carga de la lista base si hay menos de 20 usuarios
        res = client.execute("SELECT count(*) FROM usuarios")
        if res.rows[0][0] < 20:
            viejos_miembros = ["Ramón Debrot", "Yovanny Melendez", "Omar Arcano", "Jose Luis Nuñez", "Jorge Delgado", "Angel Rincón", "Carlos Rincón", "JUMAR RENGIFO", "Leonardo Rivas", "Cirpiano Heredia", "José Daniel Meza", "Marcos Penott", "Koxzartc Gonzalez", "Daninger Barreto", "Francisco Gonzalez", "Moisés Penott", "Francisco javier Rivas", "LEOPOLDO CADAVID", "YORGER MAITA", "OSCAR QUINTERO PONCE", "OSCAR QUINTERO GALLER", "LEONEL SALAZAR", "RAYMOND MURO", "Hevelmir Barreto"]
            for m in viejos_miembros:
                usr = m.replace(" ", "").lower()
                client.execute("INSERT OR IGNORE INTO usuarios (username, password, nombre_qh, grado, rol, perm_tesoreria, perm_secretaria, cargo_logia) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (usr, '123', m, 'Maestro Mason', 'Usuario', 0, 0, 'Ninguno'))
    finally:
        client.close()

init_db()

# --- 4. FUNCIONES DE APOYO Y PDF ---
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
        return float(tasa_str.replace(',', '.'))
    except: return 45.00

if 'tasa_actual' not in st.session_state:
    st.session_state.tasa_actual = obtener_tasa_bcv()

def texto_seguro(texto):
    if not texto: return ""
    return str(texto).encode('latin-1', 'replace').decode('latin-1')

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
        self.set_font('Arial', '', 8)
        self.cell(0, 5, texto_seguro('Constituida bajo los auspicios de la Muy Resp.·. Gran Logia de la República de Venezuela'), ln=True, align='C')
        self.cell(0, 5, texto_seguro('Gran Templo Masónico, Jesuítas a Maturín, No 5, Apartado 927'), ln=True, align='C')
        self.cell(0, 5, texto_seguro('CARACAS, VENEZUELA'), ln=True, align='C')
        self.ln(10)

def generar_pdf_acta(d, presentes):
    pdf = FormatoPDF(); pdf.add_page()
    pdf.set_font('Arial', 'B', 14); pdf.cell(0, 10, texto_seguro(f"ACTA DE TENIDA - {d['id_acta']}"), ln=True, align='C'); pdf.ln(5)
    
    pdf.set_font('Arial', 'B', 10); pdf.cell(40, 8, "Fecha:", 1); pdf.set_font('Arial', '', 10); pdf.cell(0, 8, f" {d['fecha']}", 1, 1)
    grado = d.get('grado_tenida', 'Aprendiz')
    pdf.set_font('Arial', 'B', 10); pdf.cell(40, 8, "Tenida:", 1); pdf.set_font('Arial', '', 10); pdf.cell(0, 8, texto_seguro(f" {d.get('tipo_tenida','')} en Grado de {grado}"), 1, 1); pdf.ln(5)
    
    pdf.set_font('Arial', 'B', 10); pdf.cell(0, 8, "Resumen / Bosquejo:", ln=True)
    pdf.set_font('Arial', '', 10); pdf.multi_cell(0, 8, texto_seguro(d['bosquejo']), border=1); pdf.ln(5)
    
    pdf.set_font('Arial', 'B', 10); pdf.cell(0, 8, texto_seguro("QQ.·.HH.·. Presentes:"), ln=True)
    pdf.set_font('Arial', '', 9)
    if presentes:
        nombres_str = ", ".join(presentes)
        pdf.multi_cell(0, 6, texto_seguro(nombres_str), border=1)
    else:
        pdf.cell(0, 8, "(No se ha registrado asistencia en el sistema para esta tenida)", border=1, ln=True)
    pdf.ln(20)
    
    pdf.cell(60, 10, "____________________", 0, 0, 'C'); pdf.cell(60, 10, "____________________", 0, 0, 'C'); pdf.cell(60, 10, "____________________", 0, 1, 'C')
    pdf.set_font('Arial', 'B', 8); pdf.cell(60, 5, "Venerable Maestro", 0, 0, 'C'); pdf.cell(60, 5, "Orador Fiscal", 0, 0, 'C'); pdf.cell(60, 5, "Secretario", 0, 1, 'C')
    
    salida = pdf.output(dest='S')
    return salida.encode('latin-1', 'replace') if isinstance(salida, str) else bytes(salida)

def generar_recibo_multiple(datos_master, items_carrito, grado_qh=""):
    pdf = FormatoPDF(); pdf.add_page()
    pdf.set_font('Arial', 'B', 12); pdf.cell(0, 10, texto_seguro(f"S.I.M.B.O.L.O. - RECIBO DE PAGO - {datos_master['qh'].upper()}"), ln=True, align='C')
    pdf.set_font('Arial', 'B', 10); pdf.cell(0, 5, f"N° LSN113-{datos_master['id']}", ln=True, align='R'); pdf.ln(5)
    
    nombre_completo = f"{grado_qh} {datos_master['qh']}" if grado_qh != "Profano" else datos_master['qh']
    pdf.cell(40, 8, "Recibido de:", 1); pdf.set_font('Arial', '', 10); pdf.cell(0, 8, texto_seguro(f" {nombre_completo}"), 1, 1)
    pdf.set_font('Arial', 'B', 10); pdf.cell(40, 8, "Fecha / Ref:", 1); pdf.set_font('Arial', '', 10); pdf.cell(0, 8, texto_seguro(f" {datos_master['fecha']} / {datos_master['ref']}"), 1, 1); pdf.ln(5)
    
    pdf.set_font('Arial', 'B', 9); pdf.set_fill_color(230, 230, 230); pdf.cell(80, 7, "Concepto", 1, 0, 'C', True); pdf.cell(50, 7, "Monto USD", 1, 0, 'C', True); pdf.cell(50, 7, "Monto Bs.", 1, 1, 'C', True)
    pdf.set_font('Arial', '', 9)
    for item in items_carrito:
        pdf.cell(80, 7, texto_seguro(f"{item['categoria']}: {item['detalle']}"), 1); pdf.cell(50, 7, f"{item['monto_usd']:,.2f} $", 1, 0, 'R'); pdf.cell(50, 7, f"{item['monto_bs']:,.2f} Bs.", 1, 1, 'R')
    
    pdf.set_font('Arial', 'B', 10); pdf.cell(80, 8, "TOTAL", 1); pdf.cell(50, 8, f"{datos_master['monto_usd']:,.2f} $", 1, 0, 'R'); pdf.cell(50, 8, f"{datos_master['monto_bs']:,.2f} Bs.", 1, 1, 'R')
    pdf.ln(15)
    
    y_actual = pdf.get_y()
    if os.path.exists("sello.png"): pdf.image("sello.png", x=40, y=y_actual, w=35)
    if os.path.exists("firma.png"): pdf.image("firma.png", x=140, y=y_actual, w=35)
    pdf.ln(35)
    
    pdf.set_font('Arial', 'B', 10); pdf.cell(0, 5, texto_seguro("Annijosé Goitia León"), ln=True, align='R')
    pdf.set_font('Arial', 'I', 9); pdf.cell(0, 5, "Tesorero", ln=True, align='R')
    
    salida = pdf.output(dest='S')
    return salida.encode('latin-1', 'replace') if isinstance(salida, str) else bytes(salida)

# --- 5. LÓGICA DE ACCESO Y SISTEMA ---
if "logged_in" not in st.session_state:
    st.title("🏛️ S.I.M.B.O.L.O. - Portal Logial")
    u = st.text_input("Usuario"); p = st.text_input("Clave", type="password")
    if st.button("Ingresar", type="primary"):
        client = get_client()
        try:
            res = client.execute("SELECT username, password, nombre_qh, grado, rol, perm_tesoreria, perm_secretaria, cargo_logia FROM usuarios WHERE username=? AND password=?", (u, p))
            if res.rows:
                row = res.rows[0]
                st.session_state["logged_in"] = True
                is_admin = 1 if row[4] == 'Administrador' else row[5]
                is_sec = 1 if row[4] == 'Administrador' else row[6]
                st.session_state["u_info"] = {"u": row[0], "nombre": row[2], "grado": row[3], "rol": row[4], "teso": is_admin, "sec": is_sec, "cargo": row[7]}
                st.rerun()
            else: st.error("Acceso denegado")
        finally:
            client.close()
else:
    info = st.session_state["u_info"]
    lista_qh, dict_grados = obtener_miembros()
    
    with st.sidebar:
        st.title("🏛️ S.I.M.B.O.L.O.")
        st.write(f"V.·.H.·. **{info['nombre']}**")
        if st.button("🚪 Cerrar Sesión", type="primary"): logout()
        
        if info['teso']:
            st.divider()
            st.header("📊 Resumen de Caja")
            df_actual = leer_datos()
            si_registrado = not df_actual[df_actual['categoria'] == 'SALDO INICIAL'].empty
            
            if not si_registrado:
                st.warning("⚠️ Pendiente Saldo Inicial")
                f_si = st.date_input("Fecha Inicio", datetime.now())
                n_bs = st.number_input("Banco (Bs)", min_value=0.0)
                n_usd = st.number_input("Caja (USD)", min_value=0.0)
                t_si = st.number_input("Tasa SI", value=st.session_state.tasa_actual)
                if st.button("💾 Guardar Saldos Iniciales"):
                    client = get_client()
                    try:
                        client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", ('SI-BS', str(f_si), 'SIMBOLO', 'INGRESO', 'SALDO INICIAL', 'Apertura Banco', 'INICIAL', 0.0, t_si, n_bs))
                        client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", ('SI-USD', str(f_si), 'SIMBOLO', 'INGRESO', 'SALDO INICIAL', 'Apertura Caja', 'EFECTIVO', n_usd, t_si, n_usd*t_si))
                    finally:
                        client.close()
                    st.rerun()
            else:
                st.success("✅ Saldo Inicial Bloqueado")
            
            b_bs = df_actual[~df_actual['referencia'].str.contains("EFECTIVO", case=False, na=False)]['monto_bs'].sum()
            c_usd = df_actual[df_actual['referencia'].str.contains("EFECTIVO", case=False, na=False)]['monto_usd'].sum()
            st.divider()
            st.metric("🏦 Banco Actual", f"{b_bs:,.2f} Bs.")
            st.metric("💵 Caja Actual", f"{c_usd:,.2f} $")

    # --- PESTAÑAS BLINDADAS ---
    m_tabs = []
    if info['rol'] != 'Administrador': m_tabs += [TAB_POR, TAB_MRE]
    if info['teso']: m_tabs += [TAB_ING, TAB_EGR, TAB_DIA, TAB_REC, TAB_DAS]
    if info['sec']: m_tabs += [TAB_ACT]
    
    is_hosp = info['cargo'] == 'Hospitalario' or info['rol'] == 'Administrador'
    if is_hosp: m_tabs += [TAB_HOS]
    
    if info['rol'] == 'Administrador': m_tabs += [TAB_USU, TAB_CON]
    
    tabs = st.tabs(m_tabs)

    # ==========================================
    # MÓDULO TESORERÍA
    # ==========================================
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
            ts_in = c_g4.number_input("Tasa BCV", value=st.session_state.tasa_actual, key=f"ts_{st.session_state.f_key}")
            
            with st.expander("➕ Añadir Concepto", expanded=True):
                c_i1, c_i2, c_i3 = st.columns([3,2,1])
                cat_t = c_i1.selectbox("Concepto", CAT_INGRESO)
                
                if cat_t == "Capitación Mensual":
                    m_list = c_i1.multiselect("Meses", MESES_ANNO)
                    d_t = ", ".join(m_list); m_t = (len(m_list)*15.0)
                elif qh_in == "CABALLERO PROFANO" and cat_t == "Derechos de Iniciación":
                    d_t = c_i1.text_input("Nombre completo del Profano", placeholder="Ej: Juan Pérez")
                    m_t = c_i1.number_input("Monto USD", value=50.0)
                elif cat_t in ["Derechos de Pasaje", "Derechos de Exaltación"]:
                    grado_dest = c_i1.selectbox("Grado a recibir", ["Compañero", "Maestro Mason"])
                    d_t = f"Aumento/Exaltación a {grado_dest}"
                    m_t = c_i1.number_input("Monto USD", value=30.0)
                else:
                    d_t = c_i1.text_input("Descripción"); m_t = c_i1.number_input("Monto USD", value=15.0)
                
                ref_t = "EFECTIVO" if met_in == "Efectivo USD" else c_i2.text_input("Ref. Pago")
                if c_i3.button("➕ Añadir"):
                    st.session_state.carrito.append({"id_t": datetime.now().strftime('%f'), "categoria": cat_t, "detalle": d_t, "monto_usd": m_t, "monto_bs": round(m_t*ts_in, 2), "ref": ref_t})
                    st.rerun()

            if st.session_state.carrito:
                for i, it in enumerate(st.session_state.carrito):
                    cols = st.columns([4,1,1,0.5])
                    cols[0].write(f"{it['categoria']}: {it['detalle']}"); cols[1].write(f"{it['monto_usd']}$"); cols[2].write(f"{it['monto_bs']}Bs")
                    if cols[3].button("🗑️", key=f"del_{it['id_t']}"): st.session_state.carrito.pop(i); st.rerun()
                if st.button("🚀 Procesar e Imprimir", type="primary", use_container_width=True):
                    id_m = datetime.now().strftime('%y%m%d%H%M%S')
                    client = get_client()
                    try:
                        for idx, item in enumerate(st.session_state.carrito):
                            client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", (f"{id_m}-{idx}", str(fecha_p), qh_in, "INGRESO", item['categoria'], item['detalle'], item['ref'], item['monto_usd'], ts_in, item['monto_bs']))
                    finally:
                        client.close()
                    
                    grado_actual = dict_grados.get(qh_in, "")
                    pdf_bytes = generar_recibo_multiple({'id': id_m, 'fecha': str(fecha_p), 'qh': qh_in, 'monto_usd': sum(x['monto_usd'] for x in st.session_state.carrito), 'monto_bs': sum(x['monto_bs'] for x in st.session_state.carrito), 'ref': ref_t}, st.session_state.carrito, grado_actual)
                    st.session_state.u_recibo = {"bytes": pdf_bytes, "n": f"Recibo_SIMBOLO_{id_m}.pdf"}
                    st.session_state.carrito = []; st.rerun()
            
            if st.session_state.u_recibo:
                st.download_button("📥 Descargar PDF", st.session_state.u_recibo['bytes'], st.session_state.u_recibo['n'], mime="application/pdf", use_container_width=True)
                if st.button("🔄 Nuevo Cobro"): st.session_state.u_recibo = None; st.session_state.f_key += 1; st.rerun()

    if TAB_EGR in m_tabs:
        with tabs[m_tabs.index(TAB_EGR)]:
            if 'eg_key' not in st.session_state: st.session_state.eg_key = 0
            st.subheader("📤 Registrar Egreso")
            c_e1, c_e2 = st.columns(2)
            f_e = c_e1.date_input("Fecha", datetime.now(), key=f"ef_{st.session_state.eg_key}")
            ben_e = c_e1.text_input("Beneficiario", key=f"eb_{st.session_state.eg_key}")
            cat_e = c_e1.selectbox("Concepto", CAT_EGRESO, key=f"ec_{st.session_state.eg_key}")
            met_e = c_e1.radio("Origen:", ["Banco (Bs)", "Caja Chica (USD)"], horizontal=True, key=f"em_{st.session_state.eg_key}")
            t_e = c_e2.number_input("Tasa", value=st.session_state.tasa_actual, key=f"et_{st.session_state.eg_key}")
            if met_e == "Caja Chica (USD)":
                m_u_e = c_e2.number_input("USD", key=f"egu_{st.session_state.eg_key}"); m_b_e = round(m_u_e * t_e, 2); r_e = "EFECTIVO"
            else:
                m_b_e = c_e2.number_input("Bs", key=f"ebs_{st.session_state.eg_key}"); m_u_e = round(m_b_e / t_e, 2); r_e = c_e2.text_input("Referencia", key=f"er_{st.session_state.eg_key}")
            nota_e = c_e2.text_input("Nota", key=f"en_{st.session_state.eg_key}")
            if st.button("Registrar Salida", type="primary"):
                id_e = f"EG-{datetime.now().strftime('%y%m%d%H%M%S')}"
                client = get_client()
                try:
                    client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", (id_e, str(f_e), ben_e, "EGRESO", cat_e, nota_e, r_e, -abs(m_u_e), t_e, -abs(m_b_e)))
                finally:
                    client.close()
                st.session_state.eg_key += 1; st.rerun()

    if TAB_DIA in m_tabs:
        with tabs[m_tabs.index(TAB_DIA)]:
            st.subheader("📖 Libro Diario")
            df_diario = leer_datos()
            st.dataframe(df_diario, use_container_width=True)
            
            if not df_diario.empty:
                st.divider()
                csv_diario = df_diario.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 Exportar Libro Diario a Excel",
                    data=csv_diario,
                    file_name=f"Libro_Diario_SIMBOLO_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )

    if TAB_REC in m_tabs:
        with tabs[m_tabs.index(TAB_REC)]:
            st.subheader("🖨️ Reimpresión")
            df_rec = leer_datos(); df_rec = df_rec[df_rec['tipo_operacion'] == 'INGRESO']
            if not df_rec.empty:
                df_rec['m_id'] = df_rec['id'].apply(lambda x: x.split('-')[0])
                id_s = st.selectbox("ID de Recibo", df_rec['m_id'].unique().tolist())
                i_r = df_rec[df_rec['m_id'] == id_s]
                l_i = [{"categoria": r['categoria'], "detalle": r['detalle'], "monto_usd": r['monto_usd'], "monto_bs": r['monto_bs']} for _, r in i_r.iterrows()]
                qh_n = i_r['origen_destino'].iloc[0]
                p_r = generar_recibo_multiple({'id': id_s, 'fecha': i_r['fecha'].iloc[0], 'qh': qh_n, 'monto_usd': i_r['monto_usd'].sum(), 'monto_bs': i_r['monto_bs'].sum(), 'ref': i_r['referencia'].iloc[0]}, l_i, dict_grados.get(qh_n, ""))
                st.download_button(f"📄 Descargar {id_s}", p_r, f"Recibo_SIMBOLO_{id_s}.pdf", mime="application/pdf")

    if TAB_DAS in m_tabs:
        with tabs[m_tabs.index(TAB_DAS)]:
            st.subheader("📊 Finanzas")
            df_r = leer_datos()
            if not df_r.empty:
                st.bar_chart(df_r.groupby('tipo_operacion')['monto_usd'].apply(lambda x: abs(x.sum())))

    # ==========================================
    # MÓDULO SECRETARÍA (UNIFICADO)
    # ==========================================
    if TAB_ACT in m_tabs:
        with tabs[m_tabs.index(TAB_ACT)]:
            st.subheader("📝 Libros de Actas y Asistencia")
            df_actas = leer_datos("actas")
            
            with st.expander("➕ Cargar Nueva Acta y Asistencia", expanded=True):
                with st.form("f_acta", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    f_a = c1.date_input("Fecha Tenida")
                    t_a = c1.selectbox("Tipo", ["Ordinaria", "Extraordinaria", "Instalación", "Fúnebre"])
                    g_a = c2.selectbox("Grado Tenida", GRADOS)
                    
                    lista_hermanos_filtro = [qh for qh in lista_qh if qh != "CABALLERO PROFANO"]
                    presentes = st.multiselect("QQ.·.HH.·. Presentes", lista_hermanos_filtro)
                    bosq = st.text_area("Bosquejo / Orden del Día")
                    
                    if st.form_submit_button("💾 Guardar Acta y Asistencia"):
                        id_a = f"ACT-{f_a.strftime('%y%m%d')}"
                        client = get_client()
                        try:
                            client.execute("INSERT OR REPLACE INTO actas VALUES (?,?,?,?,?)", (id_a, str(f_a), t_a, bosq, g_a))
                            client.execute("DELETE FROM asistencia WHERE id_acta=?", (id_a,))
                            for qh in presentes:
                                client.execute("INSERT INTO asistencia (id_acta, nombre_qh, asistio) VALUES (?,?,?)", (id_a, qh, 1))
                        finally:
                            client.close()
                        st.success(f"Acta {id_a} y Asistencia registradas."); st.rerun()

            if not df_actas.empty:
                st.divider()
                st.write("**🖨️ Generar Acta en PDF**")
                id_sel = st.selectbox("Seleccione Acta para imprimir", df_actas['id_acta'].tolist())
                acta_row = df_actas[df_actas['id_acta'] == id_sel].iloc[0]
                
                client = get_client()
                try:
                    res_asis = client.execute("SELECT nombre_qh FROM asistencia WHERE id_acta=? AND asistio=1", (id_sel,))
                    df_asis = pd.DataFrame([list(r) for r in res_asis.rows], columns=res_asis.columns)
                finally:
                    client.close()
                    
                lista_presentes = df_asis['nombre_qh'].tolist() if not df_asis.empty else []
                
                pdf_acta = generar_pdf_acta(acta_row.to_dict(), lista_presentes)
                st.download_button(f"📥 Descargar PDF Acta {id_sel}", pdf_acta, f"{id_sel}.pdf", mime="application/pdf")
                
            st.divider()
            st.subheader("📈 Reporte de Asistencia y Derecho a Voto")
            
            client = get_client()
            try:
                res_total = client.execute("SELECT count(*) as total FROM actas")
                total_actas_db = res_total.rows[0][0] if res_total.rows else 0
                
                if total_actas_db > 0:
                    query_reporte = """
                    SELECT u.nombre_qh as 'Q.·.H.·.', u.grado as 'Grado', 
                           COUNT(a.id_registro) as 'Tenidas Asistidas'
                    FROM usuarios u
                    LEFT JOIN asistencia a ON u.nombre_qh = a.nombre_qh
                    WHERE u.nombre_qh != 'CABALLERO PROFANO'
                    GROUP BY u.nombre_qh, u.grado
                    """
                    res_reporte = client.execute(query_reporte)
                    df_reporte = pd.DataFrame([list(r) for r in res_reporte.rows], columns=res_reporte.columns)
                    
                    df_reporte['Tenidas Realizadas'] = total_actas_db
                    df_reporte['% Asistencia'] = round((df_reporte['Tenidas Asistidas'] / total_actas_db) * 100, 1)
                    
                    def calcular_voto(row):
                        if row['Grado'] in ['Maestro Mason', 'Past Master']:
                            return "✅ Sí" if row['% Asistencia'] >= 50.0 else "❌ No (Falta asis.)"
                        return "❌ No (Por Grado)"
                    
                    df_reporte['Derecho a Voto (Elecciones)'] = df_reporte.apply(calcular_voto, axis=1)
                    
                    st.dataframe(df_reporte.style.format({'% Asistencia': '{:.1f}%'}), use_container_width=True)
                else:
                    st.info("Aún no se han registrado actas para calcular la asistencia.")
            finally:
                client.close()

    # ==========================================
    # MÓDULO HOSPITALARIO (SACO DE BENEFICENCIA)
    # ==========================================
    if TAB_HOS in m_tabs:
        with tabs[m_tabs.index(TAB_HOS)]:
            st.subheader("❤️ Tronco de la Viuda / Saco de Beneficencia")
            
            with st.expander("➕ Registrar Nueva Recolección", expanded=True):
                with st.form("f_hosp", clear_on_submit=True):
                    c_h1, c_h2 = st.columns(2)
                    f_h = c_h1.date_input("Fecha de Tenida", datetime.now())
                    det_h = c_h1.text_input("Detalle / N° de Tenida", placeholder="Ej. Tenida Ordinaria")
                    
                    # Ahora los campos son completamente independientes
                    m_usd_h = c_h2.number_input("Recolectado en USD ($)", min_value=0.0, step=1.0)
                    m_bs_h = c_h2.number_input("Recolectado en Bs.", min_value=0.0, step=10.0)
                    t_bcv_h = c_h2.number_input("Tasa BCV del día (Ref.)", value=st.session_state.tasa_actual)
                    
                    if st.form_submit_button("💾 Guardar Recolección"):
                        client = get_client()
                        try:
                            # Guarda exactamente lo que el Hospitalario contó en físico
                            client.execute("INSERT INTO hospitalario (fecha, detalle, monto_usd, tasa_bcv, monto_bs) VALUES (?, ?, ?, ?, ?)", (str(f_h), det_h, m_usd_h, t_bcv_h, m_bs_h))
                        finally:
                            client.close()
                        st.success("Óbolo registrado exitosamente en la bóveda del Hospitalario.")
                        st.rerun()
            
            st.divider()
            st.subheader("📖 Historial de Recolecciones")
            df_hosp = leer_datos("hospitalario")
            if not df_hosp.empty:
                st.dataframe(df_hosp[['fecha', 'detalle', 'monto_usd', 'monto_bs', 'tasa_bcv']], use_container_width=True)
                
                # Mostramos los totales ahorrados de forma independiente
                col_tot1, col_tot2 = st.columns(2)
                col_tot1.metric("Total Ahorrado (USD)", f"{df_hosp['monto_usd'].sum():,.2f} $")
                col_tot2.metric("Total Ahorrado (Bs)", f"{df_hosp['monto_bs'].sum():,.2f} Bs.")
                
                # Exportar a Excel
                st.divider()
                csv_hosp = df_hosp.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 Exportar Historial a Excel",
                    data=csv_hosp,
                    file_name=f"Hospitalario_SIMBOLO_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )
            else:
                st.info("Aún no hay fondos registrados en el Saco de Beneficencia.")

    # ==========================================
    # MÓDULO ADMINISTRADOR
    # ==========================================
    if TAB_USU in m_tabs:
        with tabs[m_tabs.index(TAB_USU)]:
            st.subheader("👥 Gestión de Usuarios")
            df_u = leer_datos("usuarios")
            st.dataframe(df_u[['username', 'nombre_qh', 'grado', 'cargo_logia', 'rol', 'perm_tesoreria', 'perm_secretaria']], use_container_width=True)
            
            c_u1, c_u2, c_u3 = st.columns(3)
            with c_u1:
                with st.expander("➕ Crear Nuevo", expanded=False):
                    with st.form("crear_u", clear_on_submit=True):
                        nu = st.text_input("Usuario (Sin espacios)")
                        np = st.text_input("Clave", type="password")
                        nn = st.text_input("Nombre Completo Q.·.H.·.")
                        ng = st.selectbox("Grado", GRADOS)
                        ncargo = st.selectbox("Cargo", CARGOS)
                        nr = st.selectbox("Rol", ["Usuario", "Administrador"])
                        pt = st.checkbox("Tesorero"); ps = st.checkbox("Secretario")
                        if st.form_submit_button("Guardar"):
                            client = get_client()
                            try:
                                client.execute("INSERT OR REPLACE INTO usuarios (username, password, nombre_qh, grado, rol, perm_tesoreria, perm_secretaria, cargo_logia) VALUES (?,?,?,?,?,?,?,?)", (nu.strip().lower(), np, nn.strip(), ng, nr, int(pt), int(ps), ncargo))
                            finally:
                                client.close()
                            st.rerun()
            with c_u2:
                with st.expander("✏️ Modificar Grado/Cargo", expanded=True):
                    with st.form("edit_u"):
                        u_mod = st.selectbox("Seleccionar Q.·.H.·.", df_u['nombre_qh'].tolist())
                        n_grado = st.selectbox("Actualizar Grado", GRADOS)
                        n_cargo = st.selectbox("Asignar Cargo", CARGOS)
                        if st.form_submit_button("Actualizar Perfil"):
                            client = get_client()
                            try:
                                client.execute("UPDATE usuarios SET grado=?, cargo_logia=? WHERE nombre_qh=?", (n_grado, n_cargo, u_mod))
                            finally:
                                client.close()
                            st.success("Perfil actualizado"); st.rerun()
            with c_u3:
                with st.expander("🔐 Cambiar Clave", expanded=False):
                    with st.form("mod_p"):
                        u_s = st.selectbox("Usuario", df_u['username'].tolist())
                        n_p = st.text_input("Nueva Clave", type="password")
                        if st.form_submit_button("Actualizar"):
                            client = get_client()
                            try:
                                client.execute("UPDATE usuarios SET password=? WHERE username=?", (n_p, u_s))
                            finally:
                                client.close()
                            st.success("Clave actualizada")

    if TAB_CON in m_tabs:
        with tabs[m_tabs.index(TAB_CON)]:
            st.subheader("⚙️ Configuración")
            st.error("⚠️ Borrado Definitivo")
            if st.checkbox("Confirmo que deseo ELIMINAR los datos"):
                if st.button("🚨 VACIAR BASE DE DATOS", type="primary"):
                    client = get_client()
                    try:
                        client.execute("DELETE FROM movimientos"); client.execute("DELETE FROM actas"); client.execute("DELETE FROM asistencia"); client.execute("DELETE FROM hospitalario")
                    finally:
                        client.close()
                    logout()

    # ==========================================
    # PORTAL DEL HERMANO (USUARIO NORMAL)
    # ==========================================
    if TAB_POR in m_tabs:
        with tabs[m_tabs.index(TAB_POR)]:
            st.subheader(f"Bienvenido al Taller, V.·.H.·. {info['nombre']}")
            
            texto_grado_cargo = f"Cámara de {info['grado']}"
            if info['cargo'] != "Ninguno": texto_grado_cargo += f" | {info['cargo']} de la Logia"
            st.write(texto_grado_cargo)
            
            df_all = leer_datos()
            mis_pagos = df_all[(df_all['origen_destino'] == info['nombre']) & (df_all['categoria'] == 'Capitación Mensual')]
            meses_pagados_str = " ".join(mis_pagos['detalle'].tolist())
            mes_actual_idx = datetime.now().month
            meses_deberian_estar_pagos = MESES_ANNO[:mes_actual_idx]
            meses_pendientes = [m for m in meses_deberian_estar_pagos if m not in meses_pagados_str]
            st.divider()
            if not meses_pendientes: st.success(f"✨ **¡ESTÁS A PLOMO!**")
            else: st.error(f"⚠️ **AVISO:** Meses pendientes: {', '.join(meses_pendientes)}")

    if TAB_MRE in m_tabs:
        with tabs[m_tabs.index(TAB_MRE)]:
            st.subheader("📄 Mis Recibos")
            df_all2 = leer_datos()
            mis_mov = df_all2[(df_all2['origen_destino'] == info['nombre']) & (df_all2['tipo_operacion'] == 'INGRESO')]
            if not mis_mov.empty:
                mis_mov['m_id'] = mis_mov['id'].apply(lambda x: x.split('-')[0])
                m_id = st.selectbox("Recibo ID", mis_mov['m_id'].unique())
                items_r = mis_mov[mis_mov['m_id'] == m_id]
                l_i = [{"categoria": r['categoria'], "detalle": r['detalle'], "monto_usd": r['monto_usd'], "monto_bs": r['monto_bs']} for _, r in items_r.iterrows()]
                pdf_b = generar_recibo_multiple({'id': m_id, 'fecha': items_r['fecha'].iloc[0], 'qh': info['nombre'], 'monto_usd': items_r['monto_usd'].sum(), 'monto_bs': items_r['monto_bs'].sum(), 'ref': items_r['referencia'].iloc[0]}, l_i, info['grado'])
                st.download_button(f"📥 Descargar PDF {m_id}", pdf_b, f"Recibo_SIMBOLO_{m_id}.pdf", mime="application/pdf")
            else: st.info("No hay pagos registrados.")
