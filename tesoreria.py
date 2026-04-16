# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import libsql_client
import requests
from bs4 import BeautifulSoup
import os
from fpdf import FPDF
import unicodedata
import hashlib
import base64
import random

# --- 1. CONFIGURACIÓN Y VERSIÓN ---
VERSION = "1.4.0-Staging"
st.set_page_config(page_title="S.I.M.B.O.L.O. - Portal Logial", layout="wide", page_icon="🏛️")

# --- 2. LISTAS MAESTRAS Y CONSTANTES ---
CAT_INGRESO = ["Capitación Mensual", "Deuda Año Anterior", "Cuota Extraordinaria", "Derechos de Iniciación", "Derechos de Pasaje", "Derechos de Exaltación", "Donación / Otros"]
CAT_EGRESO = ["Aporte Gran Logia", "Gastos de Templo", "Servicios (Luz/Agua)", "Comisión Bancaria", "Mantenimiento", "Otros"]
MESES_ANNO = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
GRADOS = ["Aprendiz", "Compañero", "Maestro Mason", "Past Master"]
CARGOS = ["Ninguno", "Venerable Maestro", "1er Vigilante", "2do Vigilante", "Orador Fiscal", "Secretario", "Tesorero", "Hospitalario", "Experto", "Maestro de Ceremonias", "Guarda Templo", "Primer Diácono", "Segundo Diácono", "Económo", "Maestro de Banquetes"]

TAB_ING = "📥 Ingresos"
TAB_EGR = "📤 Egresos"
TAB_CXC = "🧾 Cuentas x Cobrar"
TAB_DIA = "📖 Diario"
TAB_REC = "🖨️ Recibos"
TAB_DAS = "📊 Dashboards"
TAB_ACT = "📜 Actas y Asistencia"
TAB_HOS = "❤️ Hospitalario"
TAB_USU = "👥 Usuarios"
TAB_CON = "⚙️ Config"
TAB_POR = "🏠 Mi Portal"
TAB_MRE = "📄 Mis Recibos"

# --- FUNCIONES DE SEGURIDAD Y LIMPIEZA ---
def quitar_acentos(texto):
    if not texto: return ""
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('utf-8')

def hash_clave(clave):
    return hashlib.sha256(str(clave).encode('utf-8')).hexdigest()

# --- 3. CONEXIÓN A TURSO ---
def get_client():
    url = st.secrets["TURSO_DATABASE_URL"]
    token = st.secrets["TURSO_AUTH_TOKEN"]
    return libsql_client.create_client_sync(url=url, auth_token=token)

@st.cache_resource
def init_db():
    client = get_client()
    try:
        client.execute('''CREATE TABLE IF NOT EXISTS movimientos (id TEXT PRIMARY KEY, fecha TEXT, origen_destino TEXT, tipo_operacion TEXT, categoria TEXT, detalle TEXT, referencia TEXT, monto_usd REAL, tasa_bcv REAL, monto_bs REAL)''')
        client.execute('''CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, nombre_qh TEXT, grado TEXT, rol TEXT, perm_tesoreria INTEGER, perm_secretaria INTEGER, cargo_logia TEXT, estatus TEXT DEFAULT 'Activo')''')
        client.execute('''CREATE TABLE IF NOT EXISTS actas (id_acta TEXT PRIMARY KEY, fecha TEXT, tipo_tenida TEXT, bosquejo TEXT, grado_tenida TEXT)''')
        client.execute('''CREATE TABLE IF NOT EXISTS asistencia (id_registro INTEGER PRIMARY KEY AUTOINCREMENT, id_acta TEXT, nombre_qh TEXT, asistio INTEGER)''')
        client.execute('''CREATE TABLE IF NOT EXISTS hospitalario (id_registro INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, detalle TEXT, monto_usd REAL, tasa_bcv REAL, monto_bs REAL)''')
        client.execute('''CREATE TABLE IF NOT EXISTS cxc (id TEXT PRIMARY KEY, fecha TEXT, deudor TEXT, concepto TEXT, monto_usd REAL, monto_bs REAL, estatus TEXT DEFAULT 'Pendiente')''')
        client.execute('''CREATE TABLE IF NOT EXISTS soportes_bancarios (id_transaccion TEXT PRIMARY KEY, url_soporte TEXT)''')
        client.execute('''CREATE TABLE IF NOT EXISTS historial_tasas (fecha TEXT PRIMARY KEY, tasa REAL)''')
        
        try: client.execute("ALTER TABLE usuarios ADD COLUMN estatus TEXT DEFAULT 'Activo'")
        except: pass

        client.execute("INSERT OR IGNORE INTO usuarios (username, password, nombre_qh, grado, rol, perm_tesoreria, perm_secretaria, cargo_logia, estatus) VALUES ('admin', ?, 'ADMINISTRADOR GENERAL', 'Past Master', 'Administrador', 1, 1, 'Ninguno', 'Activo')", (hash_clave('113'),))
        usr_anni = quitar_acentos("Annijose Goitia".replace(" ", "").lower())
        client.execute("INSERT OR IGNORE INTO usuarios (username, password, nombre_qh, grado, rol, perm_tesoreria, perm_secretaria, cargo_logia, estatus) VALUES (?, ?, 'ANNIJOSÉ GOITIA', 'Maestro Mason', 'Administrador', 1, 1, 'Tesorero', 'Activo')", (usr_anni, hash_clave('113')))
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

def leer_datos_diario_auditoria():
    client = get_client()
    try:
        res = client.execute("SELECT m.*, s.url_soporte FROM movimientos m LEFT JOIN soportes_bancarios s ON m.id LIKE s.id_transaccion || '-%'")
        return pd.DataFrame([list(r) for r in res.rows], columns=res.columns)
    finally:
        client.close()

def obtener_miembros():
    client = get_client()
    try:
        res = client.execute("SELECT nombre_qh, grado FROM usuarios WHERE estatus='Activo' OR estatus IS NULL")
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

def registrar_tasa_historica(tasa):
    if tasa > 0:
        hoy = str(datetime.now().date())
        client = get_client()
        try: client.execute("INSERT OR IGNORE INTO historial_tasas (fecha, tasa) VALUES (?, ?)", (hoy, tasa))
        finally: client.close()

if 'tasa_actual' not in st.session_state:
    st.session_state.tasa_actual = obtener_tasa_bcv()
    registrar_tasa_historica(st.session_state.tasa_actual)

def formatear_miles(df):
    columnas_monto = ['monto_usd', 'tasa_bcv', 'monto_bs', 'equiv_usd_al_dia']
    formato = {}
    for col in columnas_monto:
        if col in df.columns:
            formato[col] = lambda x: f"{x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    return formato

def texto_seguro(texto):
    if not texto: return ""
    return str(texto).encode('latin-1', 'replace').decode('latin-1')

# --- MOTOR DE INTELIGENCIA FINANCIERA ---
def generar_reporte_inteligente(df_trim, t_ing_bs, t_egr_bs, t_ing_usd, t_egr_usd, tot_cxc_usd, tot_cxc_bs):
    if df_trim.empty:
        return "No hay suficientes datos procesados en este trimestre para generar un análisis."
    
    tasa_ref = st.session_state.tasa_actual
    total_ing_equiv_bs = t_ing_bs + (t_ing_usd * tasa_ref)
    total_egr_equiv_bs = abs(t_egr_bs) + abs(t_egr_usd * tasa_ref)
    flujo_neto = total_ing_equiv_bs - total_egr_equiv_bs
    
    analisis = "💡 **Corte Ejecutivo para la Tenida:**\n\n"
    
    if flujo_neto > 0:
        analisis += f"✅ **Estatus Operativo:** La Logia mantiene un superávit trimestral. Los ingresos totales ({total_ing_equiv_bs:,.2f} Bs. equiv.) superaron a los egresos ({total_egr_equiv_bs:,.2f} Bs. equiv.), generando un flujo de caja positivo de **{flujo_neto:,.2f} Bs.**\n\n"
    elif flujo_neto < 0:
        analisis += f"⚠️ **Alerta de Déficit:** Los egresos operativos ({total_egr_equiv_bs:,.2f} Bs. equiv.) superaron los ingresos del trimestre ({total_ing_equiv_bs:,.2f} Bs. equiv.) por una diferencia de **{abs(flujo_neto):,.2f} Bs.** Se sugiere implementar medidas de recaudación.\n\n"
    else:
        analisis += "⚖️ **Punto de Equilibrio:** Los ingresos y egresos del taller se encuentran perfectamente equilibrados.\n\n"
    
    if tot_cxc_usd > 0 or tot_cxc_bs > 0:
        analisis += f"📈 **Cuentas por Cobrar (Activos):** La Logia tiene a su favor **{tot_cxc_bs:,.2f} Bs** y **{tot_cxc_usd:,.2f} $** pendientes por recaudar.\n\n"
        
    df_egresos = df_trim[df_trim['tipo_operacion'] == 'EGRESO'].copy()
    if not df_egresos.empty:
        df_egresos['equiv_bs'] = df_egresos.apply(lambda x: abs(x['monto_bs']) if x['monto_bs'] != 0 else abs(x['monto_usd'] * x['tasa_bcv']), axis=1)
        gasto_mayor = df_egresos.groupby('categoria')['equiv_bs'].sum().idxmax()
        monto_mayor = df_egresos.groupby('categoria')['equiv_bs'].sum().max()
        analisis += f"📊 **Foco de Gastos:** El mayor desembolso de fondos de la Logia este trimestre fue destinado a la categoría **'{gasto_mayor}'** (Aprox. {monto_mayor:,.2f} Bs.).\n"
        
    return analisis

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
    
    es_historico = any("HISTÓRICA" in str(item.get('ref', '')) for item in items_carrito)
    mes_limite = "la fecha"
    meses_en_este_pago = []
    
    for it in items_carrito:
        if it['categoria'] == "Capitación Mensual":
            if "AÑO COMPLETO" in it['detalle']:
                meses_en_este_pago = MESES_ANNO
                break
            for m in MESES_ANNO:
                if m in it['detalle']: meses_en_este_pago.append(m)

    if meses_en_este_pago:
        meses_ordenados = [m for m in MESES_ANNO if m in meses_en_este_pago]
        mes_limite = meses_ordenados[-1]
        primer_mes_pago_idx = MESES_ANNO.index(meses_ordenados[0])
        meses_que_deberian_estar_pagos = MESES_ANNO[:primer_mes_pago_idx]
        
        client = get_client()
        try:
            res_prev = client.execute("SELECT detalle FROM movimientos WHERE origen_destino=? AND categoria='Capitación Mensual'", (datos_master['qh'],))
            todos_detalles_previos = " ".join([r[0] for r in res_prev.rows])
            faltan_meses_previos = any(m not in todos_detalles_previos for m in meses_que_deberian_estar_pagos)
        finally:
            client.close()

        if es_historico:
            pdf.set_text_color(180, 0, 0)
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(0, 8, texto_seguro("NOTA: ESTE ES UN REGISTRO HISTÓRICO DE MIGRACIÓN."), ln=True, align='L')
            if faltan_meses_previos and "AÑO COMPLETO" not in str(items_carrito):
                pdf.cell(0, 8, texto_seguro(f"AVISO: Existen meses anteriores pendientes en el historial."), ln=True, align='L')
            else:
                pdf.cell(0, 8, texto_seguro(f"El Q.·.H.·. se encuentra A PLOMO hasta el mes de {mes_limite}."), ln=True, align='L')
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)

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

def generar_carta_plomo_pdf(nombre_qh, cedula_qh, grado_qh, cargo_qh, mes_plomo):
    pdf = FPDF()
    pdf.add_page()
    
    if os.path.exists("logo.png"): pdf.image("logo.png", 10, 8, 25)
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 5, texto_seguro("A L.·. G.·. D.·. G.·. A.·. D.·. U.·."), ln=True, align='C')
    pdf.cell(0, 5, texto_seguro("Resp.·. Log.·. Símbolo N° 113"), ln=True, align='C')
    pdf.cell(0, 5, texto_seguro("R.·. E.·. A.·. A.·."), ln=True, align='C')
    
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 5, texto_seguro("Constituida bajo los auspicios de la muy Resp.·. Gran Logia de la República de Venezuela"), ln=True, align='C')
    pdf.cell(0, 5, texto_seguro("Gran Templo Masónico – Jesuitas a Maturín – No. 5"), ln=True, align='C')
    pdf.cell(0, 5, texto_seguro("Apartado 927 Or.·. De Caracas"), ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 5, texto_seguro("S.·. F.·. U.·.                                        L.·. I.·. F.·."), ln=True, align='C')
    pdf.ln(5)
    
    hoy = datetime.now()
    fecha_str = f"Or.·. de Caracas {hoy.day} de {MESES_ANNO[hoy.month-1].lower()} del {hoy.year} (e.·. v.·.)"
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 5, texto_seguro(fecha_str), ln=True, align='R')
    pdf.ln(10)
    
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, texto_seguro("Constancia"), ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font('Arial', '', 12)
    cargo_texto = f"ostentando el cargo de {cargo_qh}" if cargo_qh != "Ninguno" else "sin cargo en la oficialidad actual"
    
    cuerpo = (f"Hacemos saber que nuestro Q.·. H.·. {nombre_qh} C.I. {cedula_qh} poseedor del Grado de {grado_qh}, "
              f"es miembro activo de nuestro respetable taller, {cargo_texto} y no se encuentra ni Entredicho ni Penado, "
              f"quien está a plomo con el mismo hasta el mes de {mes_plomo}, por lo tanto, está en pleno goce de todos "
              f"los derechos masónicos consagrados en nuestras leyes vigentes.")
    pdf.multi_cell(0, 8, texto_seguro(cuerpo), align='J')
    pdf.ln(5)
    
    cuerpo2 = f"Dada, firmada y sellada en nuestro templo masónico, al Or.·. de Caracas, a los {hoy.day} días del mes de {MESES_ANNO[hoy.month-1]} del {hoy.year} (e.·. v.·.)"
    pdf.multi_cell(0, 8, texto_seguro(cuerpo2), align='J')
    pdf.ln(15)
    
    pdf.cell(0, 5, texto_seguro("Fraternalmente,"), ln=True, align='C')
    pdf.ln(25)
    
    y_actual = pdf.get_y()
    if os.path.exists("firma.png"): pdf.image("firma.png", x=85, y=y_actual-15, w=35)
    if os.path.exists("sello.png"): pdf.image("sello.png", x=150, y=y_actual-15, w=30)
        
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(60, 5, texto_seguro("____________________"), 0, 0, 'C')
    pdf.cell(70, 5, texto_seguro("____________________"), 0, 0, 'C')
    pdf.cell(60, 5, texto_seguro("____________________"), 0, 1, 'C')
    
    pdf.cell(60, 5, texto_seguro("Secretario"), 0, 0, 'C')
    pdf.cell(70, 5, texto_seguro("Ven.·. Maestro"), 0, 0, 'C')
    pdf.cell(60, 5, texto_seguro("Annijosé Goitia León"), 0, 1, 'C')
    
    pdf.cell(60, 5, texto_seguro(""), 0, 0, 'C')
    pdf.cell(70, 5, texto_seguro(""), 0, 0, 'C')
    pdf.cell(60, 5, texto_seguro("Tes.·."), 0, 1, 'C')
    
    salida = pdf.output(dest='S')
    return salida.encode('latin-1', 'replace') if isinstance(salida, str) else bytes(salida)

# --- 5. LÓGICA DE ACCESO Y SEGURIDAD ---
if "logged_in" not in st.session_state:
    st.title("🏛️ S.I.M.B.O.L.O. - Portal Logial")
    u = st.text_input("Usuario"); p = st.text_input("Clave", type="password")
    
    if st.button("Ingresar", type="primary"):
        if u == "arquitecto" and p == "Luz113!":
            st.session_state["logged_in"] = True
            st.session_state["u_info"] = {
                "u": "arquitecto", "nombre": "GRAN ARQUITECTO (SYSTEM)", "grado": "Past Master", 
                "rol": "Administrador", "teso": 1, "sec": 1, "cargo": "Ninguno"
            }
            st.rerun()
        else:
            client = get_client()
            try:
                res = client.execute("SELECT username, password, nombre_qh, grado, rol, perm_tesoreria, perm_secretaria, cargo_logia FROM usuarios WHERE username=? AND estatus='Activo'", (u,))
                if res.rows:
                    row = res.rows[0]; db_pwd = row[1]; hash_input = hash_clave(p)
                    if db_pwd == hash_input or db_pwd == p:
                        if db_pwd == p:
                            client.execute("UPDATE usuarios SET password=? WHERE username=?", (hash_input, u))
                        
                        st.session_state["logged_in"] = True
                        p_rol = row[4]; p_cargo = row[7]
                        p_teso = 1 if p_rol == 'Administrador' or p_cargo == 'Tesorero' else row[5]
                        p_sec = 1 if p_rol == 'Administrador' or p_cargo == 'Secretario' else row[6]
                        st.session_state["u_info"] = {"u": row[0], "nombre": row[2], "grado": row[3], "rol": p_rol, "teso": p_teso, "sec": p_sec, "cargo": p_cargo}
                        st.rerun()
                    else: st.error("Credenciales incorrectas.")
                else: st.error("Usuario no encontrado o inactivo.")
            finally: client.close()
else:
    info = st.session_state["u_info"]; lista_qh, dict_grados = obtener_miembros()
    is_hosp = info['cargo'] == 'Hospitalario' or info['rol'] == 'Administrador'
    tratamiento_masonico = "V.·.H.·." if info['grado'] in ['Maestro Mason', 'Past Master'] else "Q.·.H.·."
    
    with st.sidebar:
        st.title("🏛️ S.I.M.B.O.L.O.")
        st.write(f"{tratamiento_masonico} **{info['nombre']}**")
        if st.button("🚪 Cerrar Sesión", type="primary"): logout()
        if info['teso']:
            st.divider(); st.header("📊 Resumen de Caja")
            df_actual = leer_datos()
            si_registrado = not df_actual[df_actual['categoria'] == 'SALDO INICIAL'].empty
            if not si_registrado:
                st.warning("⚠️ Pendiente Saldo Inicial")
                f_si = st.date_input("Fecha Inicio", datetime.now())
                n_bs = st.number_input("Banco (Bs)", min_value=0.0)
                n_usd = st.number_input("Caja (USD)", min_value=0.0)
                t_si = st.number_input("Tasa SI", value=st.session_state.tasa_actual, format="%.4f")
                if st.button("💾 Guardar Saldos Iniciales"):
                    client = get_client()
                    try:
                        client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", ('SI-BS', str(f_si), 'SIMBOLO', 'INGRESO', 'SALDO INICIAL', 'Apertura Banco', 'INICIAL', 0.0, t_si, n_bs))
                        client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", ('SI-USD', str(f_si), 'SIMBOLO', 'INGRESO', 'SALDO INICIAL', 'Apertura Caja', 'EFECTIVO', n_usd, t_si, n_usd*t_si))
                    finally: client.close(); st.rerun()
            else: st.success("✅ Saldo Inicial Bloqueado")
            b_bs = df_actual[~df_actual['referencia'].str.contains("EFECTIVO", case=False, na=False)]['monto_bs'].sum()
            c_usd = df_actual[df_actual['referencia'].str.contains("EFECTIVO", case=False, na=False)]['monto_usd'].sum()
            st.metric("🏦 Banco Actual", f"{b_bs:,.2f} Bs.".replace(',', 'X').replace('.', ',').replace('X', '.'))
            st.metric("💵 Caja Actual", f"{c_usd:,.2f} $".replace(',', 'X').replace('.', ',').replace('X', '.'))
        if is_hosp:
            st.divider(); st.header("❤️ Resumen Hospitalario")
            df_hosp_all = leer_datos("hospitalario")
            si_hosp_registrado = not df_hosp_all[df_hosp_all['detalle'] == 'SALDO INICIAL'].empty
            if not si_hosp_registrado:
                st.warning("⚠️ Pendiente SI Hospitalario")
                f_si_h = st.date_input("Fecha SI Hosp", datetime.now())
                n_usd_h = st.number_input("Caja Hosp (USD)", min_value=0.0); n_bs_h = st.number_input("Caja Hosp (Bs)", min_value=0.0)
                if st.button("💾 Guardar SI Hosp"):
                    client = get_client()
                    try: client.execute("INSERT INTO hospitalario (fecha, detalle, monto_usd, tasa_bcv, monto_bs) VALUES (?, 'SALDO INICIAL', ?, ?, ?)", (str(f_si_h), n_usd_h, st.session_state.tasa_actual, n_bs_h))
                    finally: client.close(); st.rerun()
            tot_usd_h = df_hosp_all['monto_usd'].sum(); tot_bs_h = df_hosp_all['monto_bs'].sum()
            st.metric("Fondo Hosp (USD)", f"{tot_usd_h:,.2f} $".replace(',', 'X').replace('.', ',').replace('X', '.'))
            st.metric("Fondo Hosp (Bs)", f"{tot_bs_h:,.2f} Bs.".replace(',', 'X').replace('.', ',').replace('X', '.'))
            
        st.sidebar.divider()
        st.sidebar.caption(f"⚙️ S.I.M.B.O.L.O. ERP - {VERSION}")

    m_tabs = []
    if info['rol'] != 'Administrador': m_tabs += [TAB_POR, TAB_MRE]
    if info['teso']: m_tabs += [TAB_ING, TAB_EGR, TAB_CXC, TAB_DIA, TAB_REC, TAB_DAS]
    if info['sec']: m_tabs += [TAB_ACT]
    if is_hosp: m_tabs += [TAB_HOS]
    if info['rol'] == 'Administrador': m_tabs += [TAB_USU, TAB_CON]
    tabs = st.tabs(m_tabs)

    # --- PORTAL DEL HERMANO ---
    if TAB_POR in m_tabs:
        with tabs[m_tabs.index(TAB_POR)]:
            st.subheader(f"Bienvenido al Taller, {tratamiento_masonico} {info['nombre']}")
            st.write(f"Cámara de {info['grado']} | {info['cargo']} de la Logia")
            df_all = leer_datos()
            mis_pagos = df_all[(df_all['origen_destino'] == info['nombre']) & (df_all['categoria'] == 'Capitación Mensual')]
            m_pagados = " ".join(mis_pagos['detalle'].tolist())
            es_solvente_total = "AÑO COMPLETO" in m_pagados
            m_idx = datetime.now().month
            m_pend = [] if es_solvente_total else [m for m in MESES_ANNO[:m_idx] if m not in m_pagados]
            st.divider()
            if not m_pend: st.success("✨ ¡ESTÁS A PLOMO!")
            else: st.error(f"⚠️ Meses pendientes: {', '.join(m_pend)}")
            
            # --- SECCIÓN: CARTA A PLOMO (Solo Maestros) ---
            if info['grado'] in ['Maestro Mason', 'Past Master']:
                st.divider()
                st.subheader("📜 Emisión de Carta a Plomo (Grados Capitulares)")
                st.info("Como Maestro Masón, puedes generar tu Constancia validada por Tesorería y Secretaría para tus trámites capitulares.")
                
                ultimo_mes_pagado = "Ninguno"
                if es_solvente_total:
                    ultimo_mes_pagado = "Diciembre (Solvencia Anual)"
                else:
                    meses_pagos = [m for m in MESES_ANNO if m in m_pagados]
                    if meses_pagos: ultimo_mes_pagado = meses_pagos[-1]
                    
                cedula_qh = st.text_input("Cédula de Identidad (Requerida para el documento):", key="cedula_plomo")
                
                if ultimo_mes_pagado != "Ninguno":
                    if cedula_qh:
                        pdf_carta = generar_carta_plomo_pdf(info['nombre'], cedula_qh, info['grado'], info['cargo'], ultimo_mes_pagado)
                        st.download_button("📥 Descargar Carta a Plomo (PDF)", data=pdf_carta, file_name=f"Carta_Plomo_{info['nombre'].replace(' ', '_')}.pdf", mime="application/pdf", type="primary")
                else:
                    st.warning("No se registran pagos de capitación en el sistema. Debe estar a plomo para generar este documento oficial.")

    # --- INGRESOS ---
    if TAB_ING in m_tabs:
        with tabs[m_tabs.index(TAB_ING)]:
            if 'carrito' not in st.session_state: st.session_state.carrito = []
            if 'u_recibo' not in st.session_state: st.session_state.u_recibo = None
            if 'f_key' not in st.session_state: st.session_state.f_key = 0
            
            st.subheader("📝 Punto de Venta")
            
            # --- PANEL DE HISTÓRICO DE TASAS ---
            with st.expander("📅 Consultar Histórico de Tasas Guardadas", expanded=False):
                client = get_client()
                try:
                    res_t = client.execute("SELECT fecha, tasa FROM historial_tasas ORDER BY fecha DESC LIMIT 10")
                    if res_t.rows:
                        df_t = pd.DataFrame([list(r) for r in res_t.rows], columns=['Fecha', 'Tasa BCV'])
                        st.dataframe(df_t.style.format({'Tasa BCV': '{:.4f}'}), use_container_width=True)
                    else:
                        st.info("El historial comenzará a llenarse automáticamente a partir de hoy.")
                finally:
                    client.close()
                    
            c_g1, c_g2, c_g3, c_g4 = st.columns([2, 1.5, 1.5, 1])
            qh_in = c_g1.selectbox("QQ.·.HH.·.", lista_qh, key=f"qh_{st.session_state.f_key}")
            fecha_p = c_g2.date_input("Fecha Pago", datetime.now(), key=f"fp_{st.session_state.f_key}")
            met_in = c_g3.radio("Método", ["Transferencia", "Efectivo USD"], horizontal=True, key=f"mt_{st.session_state.f_key}")
            
            comision_ajuste = False
            img_file = None
            if met_in == "Transferencia":
                comision_ajuste = st.checkbox("¿Aplica Comisión 1.5%? (Otro banco)", value=True, key=f"com_{st.session_state.f_key}")
                img_file = st.file_uploader("📸 Adjuntar Comprobante (Opcional - Para Auditoría)", type=['jpg','png','jpeg'], key=f"img_{st.session_state.f_key}")
                
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
                ref_t_input = c_i2.text_input("Ref. Pago", key=f"ref_{st.session_state.f_key}")
                if es_hist: m_t_f, m_b_f, r_f = 0.0, 0.0, "MIGRACIÓN HISTÓRICA"
                else: m_t_f, m_b_f, r_f = m_t, round(m_t * ts_in, 2), "EFECTIVO" if met_in == "Efectivo USD" else ref_t_input
                if c_i3.button("➕ Añadir"):
                    st.session_state.carrito.append({"id_t": datetime.now().strftime('%f'), "categoria": cat_t, "detalle": d_t, "monto_usd": m_t_f, "monto_bs": m_b_f, "ref": r_f}); st.rerun()
            
            if st.session_state.carrito:
                for i, it in enumerate(st.session_state.carrito):
                    cols = st.columns([4,1,1,0.5]); cols[0].write(f"{it['categoria']}: {it['detalle']}"); cols[1].write(f"{it['monto_usd']}$"); cols[2].write(f"{it['monto_bs']}Bs")
                    if cols[3].button("🗑️", key=f"del_{it['id_t']}"): st.session_state.carrito.pop(i); st.rerun()
                
                if st.button("🚀 Procesar e Imprimir", type="primary", use_container_width=True):
                    id_m = datetime.now().strftime('%y%m%d%H%M%S')
                    url_final_img = ""
                    
                    if img_file:
                        with st.spinner("Subiendo soporte a la nube para auditoría..."):
                            api_key = st.secrets.get("IMGBB_API_KEY", "")
                            if api_key:
                                try:
                                    res = requests.post("https://api.imgbb.com/1/upload", data={"key": api_key, "image": base64.b64encode(img_file.read()).decode('utf-8')})
                                    if res.status_code == 200: url_final_img = res.json()['data']['url']
                                except Exception as e: st.warning(f"Error al subir imagen: {e}")
                    
                    client = get_client()
                    try:
                        for idx, item in enumerate(st.session_state.carrito):
                            client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", (f"{id_m}-{idx}", str(fecha_p), qh_in, "INGRESO", item['categoria'], item['detalle'], item['ref'], item['monto_usd'], ts_in, item['monto_bs']))
                            if met_in == "Transferencia" and not es_hist and comision_ajuste:
                                com_bs = round(item['monto_bs'] * 0.015, 2); com_usd = round(com_bs / ts_in, 2)
                                client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", (f"COM-{id_m}-{idx}", str(fecha_p), 'BBVA Provincial', 'EGRESO', 'Comisión Bancaria', f'Comisión 1.5% - Ref: {item["ref"]}', 'COMIS. CRI OB REC', -abs(com_usd), ts_in, -abs(com_bs)))
                        
                        if url_final_img:
                            client.execute("INSERT INTO soportes_bancarios (id_transaccion, url_soporte) VALUES (?,?)", (id_m, url_final_img))
                            
                    finally: client.close()
                    
                    pdf_bytes = generar_recibo_multiple({'id': id_m, 'fecha': str(fecha_p), 'qh': qh_in, 'monto_usd': sum(x['monto_usd'] for x in st.session_state.carrito), 'monto_bs': sum(x['monto_bs'] for x in st.session_state.carrito), 'ref': st.session_state.carrito[0]['ref']}, st.session_state.carrito, dict_grados.get(qh_in, ""))
                    st.session_state.u_recibo = {"bytes": pdf_bytes, "n": f"Recibo_SIMBOLO_{id_m}.pdf"}; st.session_state.carrito = []; st.session_state.f_key += 1; st.rerun()
            
            if st.session_state.u_recibo:
                st.download_button("📥 Descargar PDF", st.session_state.u_recibo['bytes'], st.session_state.u_recibo['n'], mime="application/pdf", use_container_width=True)
                if st.button("🔄 Nuevo Cobro"): st.session_state.u_recibo = None; st.rerun()

    # --- EGRESOS ---
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

    # --- CUENTAS POR COBRAR (ACTIVOS) ---
    if TAB_CXC in m_tabs:
        with tabs[m_tabs.index(TAB_CXC)]:
            st.subheader("🧾 Control de Cuentas por Cobrar (Activos)")
            
            with st.expander("➕ Registrar Nueva Deuda a Favor de la Logia", expanded=True):
                with st.form("f_cxc", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    f_cxc = c1.date_input("Fecha de Registro", datetime.now())
                    lista_deudores = lista_qh + ["CABALLERO PROFANO", "OTRO (Escribir abajo)"]
                    deudor_sel = c1.selectbox("Deudor (Quién nos debe)", lista_deudores)
                    deudor_otro = c1.text_input("Si eligió OTRO, especifique el nombre:")
                    
                    concepto_cxc = c2.text_input("Concepto / Motivo de la Deuda")
                    m_usd_cxc = c2.number_input("Monto a Cobrar (USD)", min_value=0.0)
                    m_bs_cxc = c2.number_input("Monto a Cobrar (Bs)", min_value=0.0)
                    
                    if st.form_submit_button("💾 Guardar Deuda a Favor", type="primary"):
                        deudor_final = deudor_otro.upper() if deudor_sel == "OTRO (Escribir abajo)" else deudor_sel
                        if not deudor_final or not concepto_cxc or (m_usd_cxc == 0 and m_bs_cxc == 0):
                            st.error("Por favor complete todos los campos y coloque un monto válido.")
                        else:
                            id_cxc = f"CXC-{datetime.now().strftime('%y%m%d%H%M%S')}"
                            client = get_client()
                            try:
                                client.execute("INSERT INTO cxc (id, fecha, deudor, concepto, monto_usd, monto_bs, estatus) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                                               (id_cxc, str(f_cxc), deudor_final, concepto_cxc.upper(), m_usd_cxc, m_bs_cxc, 'Pendiente'))
                            finally:
                                client.close()
                            st.success("Cuenta por Cobrar registrada correctamente.")
                            st.rerun()
            
            st.divider()
            st.write("**⚠️ Cuentas por Cobrar Pendientes**")
            df_cxc = leer_datos("cxc")
            if not df_cxc.empty:
                pendientes = df_cxc[df_cxc['estatus'] == 'Pendiente']
                if not pendientes.empty:
                    st.dataframe(pendientes.style.format({'monto_usd': '{:,.2f} $', 'monto_bs': '{:,.2f} Bs'}), use_container_width=True)
                    
                    with st.expander("✅ Procesar Cobro de Deuda (Cruza directo a Caja/Banco)", expanded=True):
                        c_p1, c_p2, c_p3 = st.columns(3)
                        id_cobrar = c_p1.selectbox("Seleccione ID de la deuda cobrada", pendientes['id'].tolist())
                        met_cobro = c_p2.radio("Método de Pago", ["Transferencia", "Efectivo USD"], key="met_cobro_cxc")
                        ref_cobro = c_p3.text_input("Referencia de Pago", key="ref_cobro_cxc")
                        
                        c_p4, c_p5, c_p6 = st.columns(3)
                        fecha_cobro = c_p4.date_input("Fecha de Cobro", datetime.now(), key="fecha_cobro_cxc")
                        tasa_cobro = c_p5.number_input("Tasa BCV del Cobro", value=st.session_state.tasa_actual, format="%.4f", key="tasa_cobro_cxc")
                        comision_cobro = c_p6.checkbox("¿Aplica Comisión 1.5%? (Otro banco)", value=True, key="com_cxc") if met_cobro == "Transferencia" else False
                        
                        if st.button("Cobrar e Ingresar a Caja", type="primary"):
                            client = get_client()
                            try:
                                res_cxc = client.execute("SELECT deudor, concepto, monto_usd, monto_bs FROM cxc WHERE id=?", (id_cobrar,))
                                if res_cxc.rows:
                                    deudor_q, concepto_q, m_usd_q, m_bs_q = res_cxc.rows[0]
                                    id_mov = f"ING-{datetime.now().strftime('%y%m%d%H%M%S')}"
                                    if m_usd_q > 0 and met_cobro == "Transferencia": monto_bs_final = round(m_usd_q * tasa_cobro, 2)
                                    else: monto_bs_final = m_bs_q
                                    ref_final = "EFECTIVO" if met_cobro == "Efectivo USD" else ref_cobro
                                    
                                    client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", 
                                                   (id_mov, str(fecha_cobro), deudor_q, "INGRESO", "Donación / Otros", f"Cobro de CXC: {concepto_q}", ref_final, m_usd_q, tasa_cobro, monto_bs_final))
                                    if met_cobro == "Transferencia" and comision_cobro:
                                        c_bs = round(monto_bs_final * 0.015, 2); c_usd = round(c_bs / tasa_cobro, 2)
                                        client.execute("INSERT INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", 
                                                       (f"COM-{id_mov}", str(fecha_cobro), 'BBVA Provincial', 'EGRESO', 'Comisión Bancaria', f'Comisión 1.5% - Ref: {ref_final}', 'COMIS. CRI OB REC', -abs(c_usd), tasa_cobro, -abs(c_bs)))
                                    
                                    client.execute("UPDATE cxc SET estatus='Cobrada' WHERE id=?", (id_cobrar,))
                                    st.success("¡Cobro procesado! La deuda está saldada y el dinero cruzó exitosamente a los Ingresos.")
                                    st.rerun()
                            finally: client.close()
                else: st.success("¡Excelente! No hay cuentas por cobrar pendientes en este momento.")
                
                with st.expander("📚 Ver Historial de Deudas Cobradas"):
                    cobradas = df_cxc[df_cxc['estatus'] == 'Cobrada']
                    if not cobradas.empty: st.dataframe(cobradas.style.format({'monto_usd': '{:,.2f} $', 'monto_bs': '{:,.2f} Bs'}), use_container_width=True)
            else: st.info("No existen registros de cuentas por cobrar en el sistema.")

    # --- DIARIO CON AUDITORÍA ---
    if TAB_DIA in m_tabs:
        with tabs[m_tabs.index(TAB_DIA)]:
            st.subheader("📖 Libro Diario (Con Auditoría de Soportes)")
            df_diario_raw = leer_datos_diario_auditoria()
            c_d1, c_d2 = st.columns(2)
            mes_sel = c_d1.selectbox("Filtrar Mes", MESES_ANNO, index=datetime.now().month-1); anno_sel = c_d2.selectbox("Año", [2025, 2026], index=1)
            
            if not df_diario_raw.empty:
                df_diario_raw['fecha_dt'] = pd.to_datetime(df_diario_raw['fecha'], errors='coerce')
                df_mes = df_diario_raw[(df_diario_raw['fecha_dt'].dt.month == MESES_ANNO.index(mes_sel)+1) & (df_diario_raw['fecha_dt'].dt.year == anno_sel)]
                
                df_mostrar = df_mes.drop(columns=['fecha_dt'])
                st.dataframe(
                    df_mostrar.style.format(formatear_miles(df_mostrar)),
                    column_config={"url_soporte": st.column_config.LinkColumn("Comprobante (Auditoría)")},
                    use_container_width=True
                )
                
                if not df_mes.empty:
                    csv_diario = df_mostrar.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(f"📥 Exportar {mes_sel} {anno_sel} a Excel", data=csv_diario, file_name=f"Libro_Diario_Auditado_{mes_sel}_{anno_sel}.csv", mime="text/csv")

    # --- RECIBOS ---
    if TAB_REC in m_tabs:
        with tabs[m_tabs.index(TAB_REC)]:
            st.subheader("🖨️ Reimpresión de Recibos"); df_rec_raw = leer_datos(); df_rec_raw = df_rec_raw[df_rec_raw['tipo_operacion'] == 'INGRESO']
            if not df_rec_raw.empty:
                df_rec_raw['m_id'] = df_rec_raw['id'].apply(lambda x: x.split('-')[0])
                opciones_recibos = {}
                for _, r in df_rec_raw.sort_values(by='fecha', ascending=False).iterrows():
                    label = f"QH: {r['origen_destino']} | Fecha: {r['fecha']} | ID: {r['m_id']}"; opciones_recibos[label] = r['m_id']
                seleccion_label = st.selectbox("Seleccione el recibo para reimprimir", list(opciones_recibos.keys()))
                id_s = opciones_recibos[seleccion_label]
                i_r = df_rec_raw[df_rec_raw['m_id'] == id_s]
                l_i = [{"categoria": r['categoria'], "detalle": r['detalle'], "monto_usd": r['monto_usd'], "monto_bs": r['monto_bs'], "ref": r['referencia']} for _, r in i_r.iterrows()]
                qh_n = i_r['origen_destino'].iloc[0]
                p_r = generar_recibo_multiple({'id': id_s, 'fecha': i_r['fecha'].iloc[0], 'qh': qh_n, 'monto_usd': i_r['monto_usd'].sum(), 'monto_bs': i_r['monto_bs'].sum(), 'ref': i_r['referencia'].iloc[0]}, l_i, dict_grados.get(qh_n, ""))
                st.download_button(f"📄 Descargar PDF de {qh_n} ({id_s})", p_r, f"Recibo_{qh_n}_{id_s}.pdf", mime="application/pdf")

    # --- DASHBOARDS ---
    if TAB_DAS in m_tabs:
        with tabs[m_tabs.index(TAB_DAS)]:
            st.title("📊 Auditoría y Balances")
            df_m = leer_datos()
            df_u = leer_datos("usuarios")
            df_u_activos = df_u[((df_u['estatus'] == 'Activo') | (df_u['estatus'].isna())) & (~df_u['nombre_qh'].isin(['CABALLERO PROFANO', 'ADMINISTRADOR GENERAL']))]
            
            df_cxc = leer_datos("cxc")
            tot_cxc_usd = 0; tot_cxc_bs = 0
            if not df_cxc.empty:
                pendientes = df_cxc[df_cxc['estatus'] == 'Pendiente']
                tot_cxc_usd = pendientes['monto_usd'].sum()
                tot_cxc_bs = pendientes['monto_bs'].sum()
            
            if tot_cxc_usd > 0 or tot_cxc_bs > 0:
                st.warning(f"🚨 **ALERTA DE CUENTAS POR COBRAR:** La Logia tiene a su favor pagos pendientes por **{tot_cxc_bs:,.2f} Bs** y **{tot_cxc_usd:,.2f} $**. Revisar pestaña 'Cuentas x Cobrar'.")

            st.subheader("🗓️ Reporte de Balance Trimestral")
            c_b1, c_b2 = st.columns(2)
            trim_sel = c_b1.selectbox("Seleccione Trimestre", ["1er Trimestre (Ene-Mar)", "2do Trimestre (Abr-Jun)", "3er Trimestre (Jul-Sep)", "4to Trimestre (Oct-Dic)"], index=1)
            año_sel = c_b2.selectbox("Año Auditoría", [2025, 2026], index=1)
            meses_trim = {"1er Trimestre (Ene-Mar)": [1, 2, 3], "2do Trimestre (Abr-Jun)": [4, 5, 6], "3er Trimestre (Jul-Sep)": [7, 8, 9], "4to Trimestre (Oct-Dic)": [10, 11, 12]}
            
            if not df_m.empty:
                df_m['fecha_dt'] = pd.to_datetime(df_m['fecha'], errors='coerce')
                df_trim = df_m[(df_m['fecha_dt'].dt.month.isin(meses_trim[trim_sel])) & (df_m['fecha_dt'].dt.year == año_sel)]
                
                df_banco = df_trim[~df_trim['referencia'].str.contains("EFECTIVO", case=False, na=False)]
                t_ing_bs = df_banco[df_banco['tipo_operacion'] == 'INGRESO']['monto_bs'].sum()
                t_egr_bs = df_banco[df_banco['tipo_operacion'] == 'EGRESO']['monto_bs'].sum()
                saldo_banco_trim = t_ing_bs + t_egr_bs
                
                df_caja = df_trim[df_trim['referencia'].str.contains("EFECTIVO", case=False, na=False)]
                t_ing_usd = df_caja[df_caja['tipo_operacion'] == 'INGRESO']['monto_usd'].sum()
                t_egr_usd = df_caja[df_caja['tipo_operacion'] == 'EGRESO']['monto_usd'].sum()
                saldo_caja_trim = t_ing_usd + t_egr_usd

                with st.expander("🤖 Análisis de Inteligencia Financiera", expanded=True):
                    st.markdown(generar_reporte_inteligente(df_trim, t_ing_bs, t_egr_bs, t_ing_usd, t_egr_usd, tot_cxc_usd, tot_cxc_bs))

                col_trim1, col_trim2, col_trim3 = st.columns(3)
                col_trim1.metric("Movimiento Banco (Bs)", f"{saldo_banco_trim:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
                col_trim2.metric("Movimiento Caja (USD)", f"{saldo_caja_trim:,.2f} $")
                col_trim3.metric("Equiv. USD Total (Tasa Actual)", f"{(saldo_banco_trim / st.session_state.tasa_actual + saldo_caja_trim):,.2f} $")
                
                st.write("**Detalle Multimoneda de Movimientos**")
                df_trim_view = df_trim.copy()
                df_trim_view['equiv_usd_al_dia'] = df_trim_view.apply(lambda x: x['monto_usd'] if x['monto_usd'] != 0 else x['monto_bs'] / x['tasa_bcv'], axis=1)
                st.dataframe(df_trim_view.drop(columns=['fecha_dt']).style.format(formatear_miles(df_trim_view)), use_container_width=True)
                csv = df_trim_view.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(f"📥 Exportar Balance a Excel", data=csv, file_name=f"Balance_{trim_sel}.csv")

            st.divider(); st.subheader("⚡ Reportes Rápidos (Movimientos Reales)")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.write("**📥 Ingresos**")
                df_ing_real = df_m[(df_m['tipo_operacion'] == 'INGRESO') & ((df_m['monto_bs'] > 0) | (df_m['monto_usd'] > 0))]
                if not df_ing_real.empty: st.dataframe(df_ing_real[['fecha', 'origen_destino', 'categoria', 'monto_usd', 'monto_bs', 'referencia']].style.format(formatear_miles(df_ing_real)), use_container_width=True)
            with col_d2:
                st.write("**📤 Egresos**")
                df_egr_real = df_m[df_m['tipo_operacion'] == 'EGRESO']
                if not df_egr_real.empty: st.dataframe(df_egr_real[['fecha', 'origen_destino', 'categoria', 'monto_usd', 'monto_bs', 'referencia']].style.format(formatear_miles(df_egr_real)), use_container_width=True)

            st.divider(); st.subheader("🗓️ Cuadro de Control de Pagos (Solvencia Anual)")
            df_p = df_m[(df_m['categoria'] == 'Capitación Mensual') & (df_m['tipo_operacion'] == 'INGRESO')]
            matriz_pagos = []
            for _, u_row in df_u_activos.iterrows():
                qh = u_row['nombre_qh']; pagos_qh = " ".join(df_p[df_p['origen_destino'] == qh]['detalle'].tolist()); fila = {'Q.·.H.·.': qh}
                es_solvente_total = "AÑO COMPLETO" in pagos_qh
                for mes in MESES_ANNO: fila[mes] = "✅" if (mes in pagos_qh or es_solvente_total) else "❌"
                matriz_pagos.append(fila)
            if matriz_pagos: st.dataframe(pd.DataFrame(matriz_pagos), use_container_width=True)
            
            st.divider(); st.subheader("📉 Índice de Morosidad por Capitación")
            tot_activos = len(df_u_activos)
            if tot_activos > 0:
                m_idx = datetime.now().month
                meses_eval = MESES_ANNO[:m_idx-1] if m_idx > 1 else []
                if meses_eval:
                    datos_deuda = []
                    for m in meses_eval:
                        pagaron = 0
                        for _, u_row in df_u_activos.iterrows():
                            pqh = " ".join(df_p[df_p['origen_destino'] == u_row['nombre_qh']]['detalle'].tolist())
                            if m in pqh or "AÑO COMPLETO" in pqh: pagaron += 1
                        mora = tot_activos - pagaron
                        p_mora = (mora / tot_activos) * 100
                        datos_deuda.append({"Mes": m, "Solventes": pagaron, "En Mora": mora, "% Deuda": p_mora})
                    df_mora = pd.DataFrame(datos_deuda)
                    col_mor1, col_mor2 = st.columns([1.5, 2])
                    with col_mor1: st.dataframe(df_mora.style.format({'% Deuda': '{:.1f}%'}), use_container_width=True)
                    with col_mor2: st.bar_chart(df_mora.set_index("Mes")[["% Deuda"]])
                else: st.success("Aún no hay meses vencidos en el año para evaluar morosidad.")

            st.divider(); st.subheader("📈 Cumplimiento de Asistencia")
            df_a = leer_datos("actas"); df_as = leer_datos("asistencia")
            if not df_a.empty and not df_as.empty:
                df_a['fecha'] = pd.to_datetime(df_a['fecha'], errors='coerce')
                df_a['mes_anio'] = df_a['fecha'].dt.strftime('%Y-%m')
                req_mensual = []
                for mes, group in df_a.groupby('mes_anio'):
                    ord_c = len(group[group['tipo_tenida'] == 'Ordinaria'])
                    ext_c = len(group[group['tipo_tenida'].isin(['Extraordinaria', 'Instalación'])])
                    req_mensual.append({'mes': mes, 'req_ap': min(2, ord_c) + ext_c, 'req_co': min(3, ord_c) + ext_c, 'req_mm': ord_c + ext_c})
                df_req = pd.DataFrame(req_mensual)
                res_asis = []
                for _, u_row in df_u_activos.iterrows():
                    qh = u_row['nombre_qh']; grado = u_row['grado']
                    req_t = df_req['req_ap'].sum() if grado == 'Aprendiz' else (df_req['req_co'].sum() if grado == 'Compañero' else df_req['req_mm'].sum())
                    asis_t = len(df_as[(df_as['nombre_qh'] == qh) & (df_as['asistio'] == 1)])
                    cumpl = (asis_t / req_t * 100) if req_t > 0 else 100.0
                    res_asis.append({'Q.·.H.·.': qh, 'Grado': grado, 'Asist. Reales': asis_t, 'Asist. Requeridas': req_t, '% Cumplimiento': min(100.0, cumpl)})
                if res_asis: st.dataframe(pd.DataFrame(res_asis).style.format({'% Cumplimiento': '{:.1f}%'}), use_container_width=True)

    # --- ACTAS Y ASISTENCIA ---
    if TAB_ACT in m_tabs:
        with tabs[m_tabs.index(TAB_ACT)]:
            st.subheader("📝 Libros de Actas y Asistencia"); df_actas = leer_datos("actas")
            with st.expander("➕ Cargar Nueva Acta y Asistencia", expanded=True):
                with st.form("f_acta", clear_on_submit=True):
                    c1, c2 = st.columns(2); f_a = c1.date_input("Fecha Tenida"); t_a = c1.selectbox("Tipo", ["Ordinaria", "Extraordinaria", "Instalación", "Fúnebre"])
                    g_a = c2.selectbox("Grado Tenida", GRADOS); lista_h_f = [qh for qh in lista_qh if qh not in ["CABALLERO PROFANO", "ADMINISTRADOR GENERAL"]]
                    pres = st.multiselect("QQ.·.HH.·. Presentes", lista_h_f); bosq = st.text_area("Bosquejo / Orden del Día")
                    if st.form_submit_button("💾 Guardar Acta"):
                        id_a = f"ACT-{f_a.strftime('%y%m%d')}"; client = get_client()
                        try:
                            client.execute("INSERT OR REPLACE INTO actas VALUES (?,?,?,?,?)", (id_a, str(f_a), t_a, bosq, g_a))
                            client.execute("DELETE FROM asistencia WHERE id_acta=?", (id_a,))
                            for qh in pres: client.execute("INSERT INTO asistencia (id_acta, nombre_qh, asistio) VALUES (?,?,?)", (id_a, qh, 1))
                        finally: client.close(); st.rerun()
            if not df_actas.empty:
                id_sel = st.selectbox("Imprimir Acta", df_actas['id_acta'].tolist())
                if st.button("Generar PDF Acta"):
                    acta_r = df_actas[df_actas['id_acta'] == id_sel].iloc[0]
                    res_as = leer_datos("asistencia"); list_pres = res_as[(res_as['id_acta'] == id_sel) & (res_as['asistio'] == 1)]['nombre_qh'].tolist()
                    pdf_a = generar_pdf_acta(acta_r.to_dict(), list_pres)
                    st.download_button(f"📥 Descargar {id_sel}", pdf_a, f"{id_sel}.pdf", mime="application/pdf")

    # --- HOSPITALARIO ---
    if TAB_HOS in m_tabs:
        with tabs[m_tabs.index(TAB_HOS)]:
            st.subheader("❤️ Tronco de la Viuda"); col_ing_h, col_egr_h = st.columns(2)
            with col_ing_h:
                with st.expander("➕ Ingreso (Óbolo)", expanded=True):
                    with st.form("f_hosp_ing", clear_on_submit=True):
                        f_h_i = st.date_input("Fecha", datetime.now(), key="fhi"); det_h_i = st.text_input("Detalle", key="dhi")
                        m_u_h_i = st.number_input("USD", min_value=0.0, key="uhi"); m_b_h_i = st.number_input("Bs", min_value=0.0, key="bhi")
                        if st.form_submit_button("💾 Guardar Ingreso"):
                            client = get_client()
                            try: client.execute("INSERT INTO hospitalario (fecha, detalle, monto_usd, tasa_bcv, monto_bs) VALUES (?, ?, ?, ?, ?)", (str(f_h_i), f"INGRESO: {det_h_i}", m_u_h_i, st.session_state.tasa_actual, m_b_h_i))
                            finally: client.close(); st.rerun()
            with col_egr_h:
                with st.expander("📤 Egreso (Ayuda)", expanded=True):
                    with st.form("f_hosp_egr", clear_on_submit=True):
                        f_h_e = st.date_input("Fecha", datetime.now(), key="fhe"); det_h_e = st.text_input("Beneficiario", key="dhe")
                        m_u_h_e = st.number_input("USD", min_value=0.0, key="uhe"); m_b_h_e = st.number_input("Bs", min_value=0.0, key="bhe")
                        if st.form_submit_button("💾 Guardar Ayuda"):
                            client = get_client()
                            try: client.execute("INSERT INTO hospitalario (fecha, detalle, monto_usd, tasa_bcv, monto_bs) VALUES (?, ?, ?, ?, ?)", (str(f_h_e), f"EGRESO: {det_h_e}", -abs(m_u_h_e), st.session_state.tasa_actual, -abs(m_b_h_e)))
                            finally: client.close(); st.rerun()
            df_h = leer_datos("hospitalario")
            if not df_h.empty: st.dataframe(df_h.style.format(formatear_miles(df_h)), use_container_width=True)

    # --- USUARIOS ---
    if TAB_USU in m_tabs:
        with tabs[m_tabs.index(TAB_USU)]:
            st.subheader("👥 Gestión de Usuarios"); df_u = leer_datos("usuarios")
            st.dataframe(df_u[['username', 'nombre_qh', 'grado', 'cargo_logia', 'rol', 'estatus']], use_container_width=True)
            c_u1, c_u2, c_u3, c_u4 = st.columns(4)
            with c_u1:
                with st.expander("➕ Crear Nuevo"):
                    with st.form("crear_u", clear_on_submit=True):
                        nu = st.text_input("Usuario"); np = st.text_input("Clave", type="password"); nn = st.text_input("Nombre Q.·.H.·.")
                        ng = st.selectbox("Grado", GRADOS); nc = st.selectbox("Cargo", CARGOS); nr = st.selectbox("Rol", ["Usuario", "Administrador"])
                        if st.form_submit_button("Guardar"):
                            client = get_client()
                            try: client.execute("INSERT OR REPLACE INTO usuarios (username, password, nombre_qh, grado, rol, perm_tesoreria, perm_secretaria, cargo_logia, estatus) VALUES (?,?,?,?,?,?,?,?,?)", (quitar_acentos(nu.lower()), hash_clave(np), nn.upper(), ng, nr, 0, 0, nc, 'Activo'))
                            finally: client.close(); st.rerun()
            with c_u2:
                with st.expander("✏️ Modificar"):
                    with st.form("edit_u", clear_on_submit=True):
                        u_m = st.selectbox("Seleccionar Q.·.H.·.", df_u['nombre_qh'].tolist()); n_g = st.selectbox("Actualizar Grado", GRADOS); n_c = st.selectbox("Asignar Cargo", CARGOS)
                        if st.form_submit_button("Actualizar"):
                            client = get_client()
                            try: client.execute("UPDATE usuarios SET grado=?, cargo_logia=? WHERE nombre_qh=?", (n_g, n_c, u_m))
                            finally: client.close(); st.success("Perfil actualizado."); st.rerun()
            with c_u3:
                with st.expander("🔐 Clave"):
                    with st.form("mod_p", clear_on_submit=True):
                        u_s = st.selectbox("Usuario", df_u['username'].tolist()); n_p = st.text_input("Nueva Clave", type="password")
                        if st.form_submit_button("Actualizar"):
                            client = get_client()
                            try: client.execute("UPDATE usuarios SET password=? WHERE username=?", (hash_clave(n_p), u_s))
                            finally: client.close(); st.success("Clave actualizada."); st.rerun()
            with c_u4:
                with st.expander("🚫 Activar/Inactivar"):
                    with st.form("status_u", clear_on_submit=True):
                        u_status = st.selectbox("Seleccionar Q.·.H.·.", df_u['nombre_qh'].tolist())
                        nuevo_estatus = st.selectbox("Estatus", ["Activo", "Inactivo"])
                        if st.form_submit_button("Actualizar Estatus", type="primary"):
                            client = get_client()
                            try: client.execute("UPDATE usuarios SET estatus=? WHERE nombre_qh=?", (nuevo_estatus, u_status))
                            finally: client.close(); st.success(f"Estatus de {u_status} actualizado a {nuevo_estatus}."); st.rerun()

    # --- CONFIGURACIÓN ---
    if TAB_CON in m_tabs:
        with tabs[m_tabs.index(TAB_CON)]:
            st.subheader("⚙️ Configuración")
            st.write("**🚨 Anulación de Movimientos Específicos**")
            df_m = leer_datos()
            if not df_m.empty:
                ops = {}
                for _, r in df_m.sort_values(by='fecha', ascending=False).iterrows():
                    if not str(r['id']).startswith("COM-"):
                        lbl = f"QH: {r['origen_destino']} | Monto: {r['monto_bs']:,.2f} Bs | Fecha: {r['fecha']} | ID: {r['id']}"
                        ops[lbl] = r['id']
                id_anul = st.selectbox("Seleccione para ANULAR", list(ops.keys()))
                if st.button("❌ ANULAR MOVIMIENTO SELECCIONADO", type="primary"):
                    client = get_client()
                    rid = ops[id_anul]
                    try: 
                        client.execute("DELETE FROM movimientos WHERE id=?", (rid,))
                        client.execute("DELETE FROM movimientos WHERE id LIKE ?", (f"COM-{rid}%",))
                        st.success("Anulado.")
                        st.rerun()
                    finally: 
                        client.close()
            st.divider()
            st.error("🚨 ZONA DE PELIGRO")
            if st.button("🔠 Convertir Nombres a MAYÚSCULAS"):
                client = get_client()
                try:
                    client.execute("UPDATE usuarios SET nombre_qh = UPPER(nombre_qh)")
                    client.execute("UPDATE movimientos SET origen_destino = UPPER(origen_destino)")
                    client.execute("UPDATE asistencia SET nombre_qh = UPPER(nombre_qh)")
                    client.execute("UPDATE cxc SET deudor = UPPER(deudor)")
                    try: client.execute("UPDATE pagos_reportados SET nombre_qh = UPPER(nombre_qh)")
                    except: pass
                    st.success("Todos los nombres convertidos a MAYÚSCULAS exitosamente.")
                finally: 
                    client.close()
                    st.rerun()
            if st.checkbox("Confirmo que deseo ELIMINAR los datos"):
                if st.button("VACIAR TODA LA BASE DE DATOS"):
                    client = get_client()
                    try:
                        for t in ["movimientos", "actas", "asistencia", "hospitalario", "cxc", "soportes_bancarios", "historial_tasas"]: 
                            try: client.execute(f"DELETE FROM {t}")
                            except: pass
                    finally: 
                        client.close()
                        logout()

            # --- BOTÓN DE INYECCIÓN DE DEMO ---
            st.divider()
            st.warning("🧪 ZONA DE DEMO / STAGING")
            if st.button("🚀 INYECTAR DATOS DE PRUEBA (QQ.·.HH.·. y Pagos)", type="primary"):
                client = get_client()
                try:
                    nombres_demo = [
                        ("FRANCISCO DE MIRANDA", "Past Master", "Venerable Maestro", "Administrador"),
                        ("ANTONIO JOSE DE SUCRE", "Maestro Mason", "1er Vigilante", "Usuario"),
                        ("SIMON BOLIVAR", "Maestro Mason", "2do Vigilante", "Usuario"),
                        ("ANDRES BELLO", "Maestro Mason", "Orador Fiscal", "Usuario"),
                        ("JOSE MARIA VARGAS", "Maestro Mason", "Secretario", "Usuario"),
                        ("ARTURO MICHELENA", "Maestro Mason", "Hospitalario", "Usuario"),
                        ("JACINTO CONVIT", "Maestro Mason", "Experto", "Usuario"),
                        ("RAUL LEONI", "Compañero", "Ninguno", "Usuario"),
                        ("ROMULO GALLEGOS", "Compañero", "Ninguno", "Usuario"),
                        ("CARLOS CRUZ-DIEZ", "Aprendiz", "Ninguno", "Usuario")
                    ]
                    clave_hash = hash_clave("123")
                    
                    for nombre, grado, cargo, rol in nombres_demo:
                        username = nombre.lower().replace(" ", "")
                        client.execute("INSERT OR IGNORE INTO usuarios (username, password, nombre_qh, grado, rol, perm_tesoreria, perm_secretaria, cargo_logia, estatus) VALUES (?, ?, ?, ?, ?, 0, 0, ?, 'Activo')", (username, clave_hash, nombre, grado, rol, cargo))

                    meses = ["Enero", "Febrero", "Marzo", "Abril"]
                    client.execute("INSERT OR IGNORE INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", ('SI-DEMO-1', str(datetime.now().date()), 'SIMBOLO', 'INGRESO', 'SALDO INICIAL', 'Apertura Banco', 'INICIAL', 0.0, 45.00, 1500.00))
                    
                    for i, (nombre, _, _, _) in enumerate(nombres_demo[:6]):
                        meses_pagados = random.sample(meses, random.randint(1, 3))
                        for mes in meses_pagados:
                            fecha_pago = (datetime.now() - timedelta(days=random.randint(1, 60))).strftime('%Y-%m-%d')
                            client.execute("INSERT OR IGNORE INTO movimientos VALUES (?,?,?,?,?,?,?,?,?,?)", (f"DEMO-{i}-{mes}", fecha_pago, nombre, "INGRESO", "Capitación Mensual", mes, f"REF-{random.randint(1000,9999)}", 0.0, 45.5, 682.5))
                    
                    st.success("✅ ¡Datos inyectados exitosamente! Ve a la pestaña de Dashboards para ver la magia.")
                finally:
                    client.close()

    # --- MIS RECIBOS ---
    if TAB_MRE in m_tabs:
        with tabs[m_tabs.index(TAB_MRE)]:
            st.subheader("📄 Mis Recibos"); df_all2 = leer_datos()
            mis_mov_raw = df_all2[(df_all2['origen_destino'] == info['nombre']) & (df_all2['tipo_operacion'] == 'INGRESO')]
            if not mis_mov_raw.empty:
                mis_mov_raw['m_id'] = mis_mov_raw['id'].apply(lambda x: str(x).split('-')[0])
                opciones_propias = {}
                for _, r in mis_mov_raw.sort_values(by='fecha', ascending=False).iterrows():
                    label = f"Fecha: {r['fecha']} | ID: {r['m_id']}"
                    opciones_propias[label] = r['m_id']
                seleccion_mre = st.selectbox("Seleccione Recibo para descargar", list(opciones_propias.keys()))
                m_id = opciones_propias[seleccion_mre]
                items_r = mis_mov_raw[mis_mov_raw['m_id'] == m_id]
                l_i = [{"categoria": r['categoria'], "detalle": r['detalle'], "monto_usd": r['monto_usd'], "monto_bs": r['monto_bs'], "ref": r['referencia']} for _, r in items_r.iterrows()]
                pdf_b = generar_recibo_multiple({'id': m_id, 'fecha': items_r['fecha'].iloc[0], 'qh': info['nombre'], 'monto_usd': items_r['monto_usd'].sum(), 'monto_bs': items_r['monto_bs'].sum(), 'ref': items_r['referencia'].iloc[0]}, l_i, info['grado'])
                st.download_button(f"📥 Descargar PDF {m_id}", pdf_b, f"Recibo_{m_id}.pdf", mime="application/pdf")
            else:
                st.info("No tienes pagos registrados en el sistema.")
