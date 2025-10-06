# -*- coding: utf-8 -*-
"""
Aplicación Streamlit Unificada para Gestión de Inventario con IA.
Combina el reconocimiento de objetos con la gestión de pedidos,
utilizando Firebase como base de datos central.
"""
import streamlit as st
from PIL import Image
import numpy as np
import cv2
import pandas as pd
import plotly.express as px
import json
from collections import Counter
import random

# --- Importaciones de utilidades y dependencias ---
from firebase_utils import FirebaseManager
from gemini_utils import GeminiUtils
from ultralytics import YOLO

try:
    from twilio.rest import Client
    from twilio.base.exceptions import TwilioRestException
    IS_TWILIO_AVAILABLE = True
except ImportError:
    IS_TWILIO_AVAILABLE = False
    Client, TwilioRestException = None, None

# --- CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(
    page_title="Sistema de Inventario IA Total",
    page_icon="🌟",
    layout="wide"
)

st.markdown("""
<style>
    .main-header { font-size: 2.5rem; color: #2a9d8f; text-align: center; margin-bottom: 1.5rem; }
    .st-emotion-cache-16txtl3 { padding-top: 2rem; }
    .report-box { background-color: #f0f2f6; padding: 1.5rem; border-radius: 10px; border-left: 6px solid #2a9d8f; margin-bottom: 1rem;}
    .report-header { font-size: 1.2rem; font-weight: bold; color: #333; }
    .report-data { font-size: 1.1rem; color: #555; }
</style>
""", unsafe_allow_html=True)

# --- INICIALIZACIÓN DE SERVICIOS (Cache para eficiencia) ---
@st.cache_resource
def initialize_services():
    """Carga modelos y establece conexiones a servicios una sola vez."""
    try:
        yolo_model = YOLO('yolov8m.pt')
        firebase_handler = FirebaseManager()
        gemini_handler = GeminiUtils()
        return yolo_model, firebase_handler, gemini_handler
    except Exception as e:
        st.error(f"**Error Crítico de Inicialización.** No se pudo cargar un modelo o conectar a un servicio. Revisa los logs y tus secrets.")
        st.code(f"Detalle: {e}", language="bash")
        return None, None, None

yolo_model, firebase, gemini = initialize_services()

if not all([yolo_model, firebase, gemini]):
    st.stop()
    
# --- LÓGICA DE TWILIO PARA NOTIFICACIONES ---
def inicializar_twilio_client():
    if not IS_TWILIO_AVAILABLE:
        st.session_state.twilio_status = "Librería no encontrada."
        return None
    try:
        if hasattr(st, 'secrets') and all(k in st.secrets for k in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"]):
            account_sid = st.secrets["TWILIO_ACCOUNT_SID"]
            auth_token = st.secrets["TWILIO_AUTH_TOKEN"]
            client = Client(account_sid, auth_token)
            st.session_state.twilio_status = "✅ Conectado"
            return client
    except Exception as e:
        st.session_state.twilio_status = f"🚨 Error: {e}"
    return None

if 'twilio_client' not in st.session_state:
    st.session_state.twilio_client = inicializar_twilio_client()

def enviar_alerta_whatsapp(mensaje):
    client = st.session_state.twilio_client
    if not client:
        st.warning("Cliente de Twilio no inicializado. No se pueden enviar alertas.")
        return False
    try:
        from_number = st.secrets["TWILIO_WHATSAPP_FROM_NUMBER"]
        to_number = st.secrets["DESTINATION_WHATSAPP_NUMBER"]
        mensaje_final = f"Your Twilio code is {random.randint(1000,9999)}\n\n{mensaje}"
        message = client.messages.create(from_=f'whatsapp:{from_number}', body=mensaje_final, to=f'whatsapp:{to_number}')
        st.toast("¡Alerta de WhatsApp enviada!", icon="📲")
        return True
    except TwilioRestException as e:
        st.error(f"Error de Twilio: {e.msg}", icon="🚨")
        if e.code == 21608: st.warning("Reactiva tu Sandbox de WhatsApp.", icon="📱")
    except Exception as e:
        st.error(f"Error inesperado al enviar WhatsApp: {e}", icon="🚨")
    return False

# --- BARRA LATERAL DE NAVEGACIÓN ---
st.sidebar.title("Navegación del Sistema")
page = st.sidebar.radio(
    "Selecciona una sección:",
    ["🏠 Inicio", "📸 Análisis de Imagen", "📦 Gestión de Inventario", "🛒 Gestión de Pedidos", "📊 Dashboard", "👥 Acerca de"]
)

# --- LÓGICA DE LAS PÁGINAS ---

if page == "🏠 Inicio":
    st.markdown('<h1 class="main-header">🌟 Bienvenido al Sistema de Inventario Total</h1>', unsafe_allow_html=True)
    st.subheader("Una solución unificada que integra IA para reconocimiento y gestión completa de inventario y pedidos.")
    st.markdown("---")
    
    try:
        items = firebase.get_all_inventory_items()
        orders = firebase.get_orders(status=None)
        item_count = len(items)
        processing_orders = len([o for o in orders if o.get('status') == 'processing'])
        
        col1, col2, col3 = st.columns(3)
        col1.metric("📦 Artículos en Inventario", item_count)
        col2.metric("⏳ Pedidos en Proceso", processing_orders)
        col3.metric("✅ Pedidos Completados", len([o for o in orders if o.get('status') == 'completed']))
    except Exception as e:
        st.warning(f"No se pudieron cargar las estadísticas: {e}")
    
    st.markdown("---")
    st.subheader("Funcionalidades Principales:")
    st.markdown("""
    - **Análisis de Imagen**: Usa la IA de Gemini para identificar, contar y categorizar productos automáticamente.
    - **Gestión de Inventario**: Añade, busca y elimina artículos de tu inventario en tiempo real a través de Firebase.
    - **Gestión de Pedidos**: Crea nuevos pedidos, procesalos descontando el stock automáticamente y mantén un historial.
    - **Dashboard**: Visualiza la composición y actividad de tu inventario con gráficos interactivos.
    - **Alertas**: Recibe notificaciones por WhatsApp cuando se crean o completan pedidos.
    """)

elif page == "📸 Análisis de Imagen":
    st.header("📸 Detección y Análisis de Objetos por Imagen")

    if 'analysis_in_progress' in st.session_state and st.session_state.analysis_in_progress:
        st.subheader("✔️ Resultado del Análisis de Gemini")
        analysis_text = st.session_state.last_analysis
        
        try:
            clean_json_str = analysis_text.strip().replace("```json", "").replace("```", "")
            analysis_data = json.loads(clean_json_str)
            
            if "error" not in analysis_data:
                st.markdown('<div class="report-box">', unsafe_allow_html=True)
                st.write(f"<span class='report-header'>Elemento:</span> <span class='report-data'>{analysis_data.get('elemento_identificado', 'N/A')}</span>", unsafe_allow_html=True)
                st.write(f"<span class='report-header'>Cantidad:</span> <span class='report-data'>{analysis_data.get('cantidad_aproximada', 'N/A')}</span>", unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

                with st.form("save_to_db_form"):
                    st.subheader("💾 Registrar en Inventario")
                    custom_id = st.text_input("ID Personalizado (SKU):", key="custom_id")
                    description = st.text_input("Descripción:", value=analysis_data.get('elemento_identificado', ''))
                    quantity = st.number_input("Unidades:", min_value=1, value=analysis_data.get('cantidad_aproximada', 1), step=1)
                    
                    if st.form_submit_button("Añadir a la Base de Datos"):
                        if not custom_id or not description:
                            st.warning("El ID y la Descripción son obligatorios.")
                        else:
                            with st.spinner("Guardando..."):
                                data_to_save = {
                                    "name": description,
                                    "quantity": quantity,
                                    "tipo": "imagen",
                                    "analisis_ia": analysis_data
                                }
                                firebase.save_inventory_item(data_to_save, custom_id)
                                st.success(f"¡Artículo '{description}' guardado con éxito!")
                                st.session_state.analysis_in_progress = False
                                st.rerun()
            else:
                 st.error(f"Error de Gemini: {analysis_data['error']}")
        except json.JSONDecodeError:
            st.error("La IA devolvió un formato inesperado.")
            st.code(analysis_text, language='text')

        if st.button("↩️ Analizar otra imagen"):
            st.session_state.analysis_in_progress = False; st.rerun()
    else:
        img_source = st.radio("Fuente de la imagen:", ["Cámara", "Subir archivo"], horizontal=True)
        img_buffer = None
        if img_source == "Cámara": img_buffer = st.camera_input("Apunta la cámara", key="camera_input")
        else: img_buffer = st.file_uploader("Sube una imagen", type=['png', 'jpg'], key="file_uploader")

        if img_buffer:
            pil_image = Image.open(img_buffer)
            with st.spinner("🧠 Detectando objetos con IA local (YOLO)..."):
                results = yolo_model(pil_image)

            st.image(results[0].plot(), caption="Objetos detectados por YOLO.", use_container_width=True)
            
            detections = results[0]
            if detections.boxes:
                for i, box in enumerate(detections.boxes):
                    class_name = detections.names[box.cls[0].item()]
                    if st.button(f"Analizar '{class_name}' #{i+1}", key=f"classify_{i}"):
                        coords = box.xyxy[0].cpu().numpy().astype(int)
                        cropped_pil_image = pil_image.crop(tuple(coords))
                        with st.spinner("🤖 Gemini está analizando..."):
                            analysis_text = gemini.analyze_image(cropped_pil_image, f"Objeto: {class_name}")
                            st.session_state.last_analysis = analysis_text
                            st.session_state.analysis_in_progress = True
                            st.rerun()

elif page == "📦 Gestión de Inventario":
    st.header("📦 Gestión de la Base de Datos de Inventario")

    with st.expander("➕ Añadir Artículo Manualmente"):
        with st.form("manual_add_form"):
            custom_id = st.text_input("ID Personalizado (SKU, Código, etc.)")
            name = st.text_input("Nombre o Descripción")
            quantity = st.number_input("Cantidad", min_value=0, step=1)
            
            if st.form_submit_button("Guardar Artículo"):
                if not custom_id or not name:
                    st.warning("El ID y el Nombre son obligatorios.")
                else:
                    data = {"name": name, "quantity": quantity, "tipo": "manual"}
                    try:
                        firebase.save_inventory_item(data, custom_id)
                        st.success(f"Artículo '{name}' guardado.")
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")

    st.markdown("---")
    st.subheader("Inventario Actual en Firebase")

    if st.button("🔄 Refrescar Datos"): st.rerun()

    try:
        with st.spinner("Cargando inventario..."):
            items = firebase.get_all_inventory_items()
        
        if items:
            df_items = pd.DataFrame(items)
            st.dataframe(df_items[['id', 'name', 'quantity', 'tipo']], use_container_width=True, hide_index=True)

            item_to_delete = st.selectbox("Selecciona un artículo para eliminar (opcional)", [""] + [f"{item['name']} ({item['id']})" for item in items])
            if item_to_delete:
                item_id_to_delete = item_to_delete.split('(')[-1].replace(')','')
                if st.button(f"🗑️ Eliminar '{item_to_delete}'", type="primary"):
                    firebase.delete_inventory_item(item_id_to_delete)
                    st.success(f"Artículo eliminado.")
                    st.rerun()
        else:
            st.warning("El inventario está vacío.")
            
    except Exception as e:
        st.error(f"No se pudo conectar con la base de datos: {e}")

elif page == "🛒 Gestión de Pedidos":
    st.header("🛒 Gestión de Pedidos", divider="green")
    
    inventory_items = firebase.get_all_inventory_items()
    
    if inventory_items:
        inventory_map = {item['name']: item['id'] for item in inventory_items}
        inventory_names = [""] + sorted(inventory_map.keys())
    else:
        inventory_map = {}
        inventory_names = [""]
        st.warning("No hay artículos en el inventario para crear pedidos.", icon="📦")


    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.subheader("📝 Crear Nuevo Pedido")
        if 'order_ingredients' not in st.session_state: 
            st.session_state.order_ingredients = [{'name': '', 'quantity': 1, 'id': None}]

        for i, ing in enumerate(st.session_state.order_ingredients):
            c1, c2, c3 = st.columns([3, 1, 1])
            selected_name = c1.selectbox(f"Ingrediente {i+1}", inventory_names, key=f"ing_name_{i}", index=inventory_names.index(ing['name']) if ing['name'] in inventory_names else 0)
            
            # CORRECCIÓN: Al seleccionar un nombre, guardamos el nombre Y el ID correspondiente
            ing['name'] = selected_name
            ing['id'] = inventory_map.get(selected_name)
            
            ing['quantity'] = c2.number_input("Cant.", min_value=1, step=1, key=f"ing_qty_{i}", value=ing['quantity'])
            if c3.button("➖", key=f"del_ing_{i}"):
                st.session_state.order_ingredients.pop(i); st.rerun()
        
        if st.button("Añadir Ingrediente", use_container_width=True):
            st.session_state.order_ingredients.append({'name': '', 'quantity': 1, 'id': None}); st.rerun()

        with st.form("order_form", clear_on_submit=True):
            title = st.text_input("Título del Pedido")
            price = st.number_input("Precio de Venta ($)", min_value=0.01, format="%.2f")
            if st.form_submit_button("Crear Pedido", type="primary", use_container_width=True):
                # CORRECCIÓN: Nos aseguramos de que el ingrediente tenga un ID válido
                valid_ings = [ing for ing in st.session_state.order_ingredients if ing['id']]
                if not title or price <= 0 or not valid_ings:
                    st.error("El pedido debe tener título, precio e ingredientes válidos.")
                else:
                    order_data = {'title': title, 'price': price, 'ingredients': valid_ings, 'status': 'processing'}
                    firebase.create_order(order_data)
                    st.success(f"Pedido '{title}' creado.")
                    enviar_alerta_whatsapp(f"🧾 Nuevo Pedido: {title} por ${price:.2f}")
                    st.session_state.order_ingredients = [{'name': '', 'quantity': 1, 'id': None}]; st.rerun()

    with col2:
        st.subheader("⏳ Pedidos en Proceso")
        processing_orders = firebase.get_orders(status='processing')
        if not processing_orders:
            st.info("No hay pedidos en proceso.")
        for order in processing_orders:
            with st.container(border=True):
                st.subheader(f"{order['title']} - ${order.get('price', 0):.2f}")
                st.caption(f"Ing: {', '.join([f'{i['name']} (x{i['quantity']})' for i in order['ingredients']])}")
                b1, b2 = st.columns(2)
                if b1.button("✅ Completar", key=f"comp_{order['id']}", type="primary", use_container_width=True):
                    with st.spinner("Procesando..."):
                        success, message = firebase.complete_order(order['id'])
                    if success:
                        st.success(message)
                        enviar_alerta_whatsapp(f"✅ Pedido Completado: {order['title']}")
                        st.rerun()
                    else:
                        st.warning(message)
                if b2.button("❌ Cancelar", key=f"canc_{order['id']}", use_container_width=True):
                    firebase.cancel_order(order['id']); st.rerun()

    st.markdown("---")
    st.subheader("✅ Historial de Pedidos Completados")
    completed_orders = firebase.get_orders(status='completed')
    if completed_orders:
        df_completed = pd.DataFrame(completed_orders)
        st.dataframe(df_completed[['id', 'title', 'price']], use_container_width=True, hide_index=True)
    else:
        st.info("No hay pedidos en el historial.")

elif page == "📊 Dashboard":
    st.header("📊 Dashboard del Inventario")
    try:
        with st.spinner("Generando estadísticas..."):
            items = firebase.get_all_inventory_items()
        
        if items:
            df = pd.DataFrame(items)
            
            st.subheader("Distribución de Artículos por Tipo de Registro")
            type_counts = df['tipo'].value_counts()
            fig_pie = px.pie(
                type_counts, 
                values=type_counts.values, 
                names=type_counts.index, 
                title="Tipos de Registros en el Inventario",
                color_discrete_sequence=px.colors.sequential.Teal
            )
            st.plotly_chart(fig_pie, use_container_width=True)

            st.subheader("Cantidad de Unidades por Artículo")
            df_quant = df.sort_values('quantity', ascending=False)
            fig_bar = px.bar(
                df_quant,
                x='name',
                y='quantity',
                title='Stock por Artículo',
                labels={'name':'Artículo', 'quantity':'Cantidad'}
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.warning("No hay datos en el inventario para generar un dashboard.")
    except Exception as e:
        st.error(f"Error al crear el dashboard: {e}")

elif page == "👥 Acerca de":
    st.header("👥 Sobre el Proyecto y sus Creadores")
    with st.container(border=True):
        col_img_est, col_info_est = st.columns([1, 3])
        with col_img_est:
            st.image("https://placehold.co/250x250/000000/FFFFFF?text=J.S.", caption="Joseph Javier Sánchez Acuña")
        with col_info_est:
            st.title("Joseph Javier Sánchez Acuña")
            st.subheader("_Estudiante de Ingeniería Industrial_")
            st.subheader("_Experto en Inteligencia Artificial y Desarrollo de Software._")
            st.markdown(
                """
                - 🔗 **LinkedIn:** [joseph-javier-sánchez-acuña](https://www.linkedin.com/in/joseph-javier-sánchez-acuña-150410275)
                - 📂 **GitHub:** [GIUSEPPESAN21](https://github.com/GIUSEPPESAN21)
                - 📧 **Email:** [joseph.sanchez@uniminuto.edu.co](mailto:joseph.sanchez@uniminuto.edu.co)
                """
            )
