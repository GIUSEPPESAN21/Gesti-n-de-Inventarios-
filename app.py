# -*- coding: utf-8 -*-
"""
Aplicación Streamlit para la Gestión de Inventarios y Pedidos.

Versión 2.0: Se reestructura la interfaz a un sistema de pestañas,
añadiendo una sección "Acerca de" para la información del autor.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib import colors

# --- Lógica de Negocio y Manejo de Datos ---

class InventoryManager:
    """
    Clase para manejar toda la lógica del inventario y los pedidos.
    """
    def __init__(self):
        # Utiliza st.session_state para mantener los datos entre interacciones
        if 'inventory_df' not in st.session_state:
            st.session_state.inventory_df = pd.DataFrame([
                {'id': 1, 'name': 'Camaron', 'quantity': 10},
                {'id': 2, 'name': 'Mojarra', 'quantity': 8},
                {'id': 3, 'name': 'Arroz', 'quantity': 500},
                {'id': 4, 'name': 'Cebolla', 'quantity': 5}
            ])
        if 'orders_df' not in st.session_state:
            st.session_state.orders_df = pd.DataFrame(columns=[
                'id', 'title', 'price', 'ingredients', 'status'
            ])
        if 'next_inventory_id' not in st.session_state:
            st.session_state.next_inventory_id = 5
        if 'next_order_id' not in st.session_state:
            st.session_state.next_order_id = 1
        
        self.LOW_STOCK_THRESHOLD = 10

    def get_inventory(self):
        return st.session_state.inventory_df.sort_values('name').reset_index(drop=True)

    def add_inventory_item(self, name, quantity):
        name = name.strip()
        if not name or quantity <= 0:
            st.error("El nombre no puede estar vacío y la cantidad debe ser positiva.")
            return

        normalized_name = name.lower()
        existing_items = st.session_state.inventory_df[st.session_state.inventory_df['name'].str.lower() == normalized_name]

        if not existing_items.empty:
            idx = existing_items.index[0]
            st.session_state.inventory_df.loc[idx, 'quantity'] += quantity
            st.toast(f"Stock de '{name}' actualizado.", icon="📦")
        else:
            new_item = pd.DataFrame([{
                'id': st.session_state.next_inventory_id,
                'name': name,
                'quantity': quantity
            }])
            st.session_state.inventory_df = pd.concat([st.session_state.inventory_df, new_item], ignore_index=True)
            st.session_state.next_inventory_id += 1
            st.toast(f"Item '{name}' agregado al inventario.", icon="✨")

    def create_order(self, title, price, ingredients):
        if not title or price <= 0 or not ingredients:
            st.error("El pedido debe tener un título, precio positivo y al menos un ingrediente.")
            return

        new_order = pd.DataFrame([{
            'id': st.session_state.next_order_id,
            'title': title,
            'price': price,
            'ingredients': ingredients,
            'status': 'processing'
        }])
        st.session_state.orders_df = pd.concat([st.session_state.orders_df, new_order], ignore_index=True)
        st.session_state.next_order_id += 1
        st.toast(f"Pedido '{title}' creado exitosamente.", icon="🧾")
        return True

    def complete_order(self, order_id):
        order_idx = st.session_state.orders_df[st.session_state.orders_df['id'] == order_id].index
        if order_idx.empty: return

        order = st.session_state.orders_df.loc[order_idx[0]]
        
        missing_items = []
        for ing in order['ingredients']:
            item_name_lower = ing['name'].lower()
            inv_item_series = st.session_state.inventory_df[st.session_state.inventory_df['name'].str.lower() == item_name_lower]
            if inv_item_series.empty or inv_item_series.iloc[0]['quantity'] < ing['quantity']:
                current_qty = 0 if inv_item_series.empty else inv_item_series.iloc[0]['quantity']
                missing_items.append(f"{ing['name']} (necesita {ing['quantity']}, disponible {current_qty})")

        if missing_items:
            st.warning(f"Stock insuficiente para '{order['title']}': {', '.join(missing_items)}")
            return

        low_stock_alerts = []
        for ing in order['ingredients']:
            item_name_lower = ing['name'].lower()
            inv_idx = st.session_state.inventory_df[st.session_state.inventory_df['name'].str.lower() == item_name_lower].index[0]
            st.session_state.inventory_df.loc[inv_idx, 'quantity'] -= ing['quantity']
            
            new_qty = st.session_state.inventory_df.loc[inv_idx, 'quantity']
            if new_qty < self.LOW_STOCK_THRESHOLD:
                low_stock_alerts.append(f"{st.session_state.inventory_df.loc[inv_idx, 'name']}: {new_qty} restantes")

        st.session_state.orders_df.loc[order_idx, 'status'] = 'completed'
        st.toast(f"Pedido '{order['title']}' completado.", icon="✅")

        if low_stock_alerts:
            st.warning(f"Alerta de bajo stock: {', '.join(low_stock_alerts)}")

    def cancel_order(self, order_id):
        st.session_state.orders_df = st.session_state.orders_df[st.session_state.orders_df['id'] != order_id]
        st.toast(f"Pedido #{order_id} cancelado.", icon="🗑️")

    def get_report(self):
        completed_orders = st.session_state.orders_df[st.session_state.orders_df['status'] == 'completed']
        total_sales = completed_orders['price'].sum()
        final_inventory = self.get_inventory()
        return {'total_sales': total_sales, 'final_inventory': final_inventory}

# --- Funciones de Generación de PDF ---
def generate_inventory_pdf(inventory_df, low_stock_threshold):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [Paragraph("Reporte de Inventario", styles['h1']), Spacer(1, 0.2 * inch)]
    table_data = [['ID', 'Nombre', 'Cantidad']]
    for _, row in inventory_df.iterrows():
        name = f"⚠️ {row['name']} (Bajo Stock!)" if row['quantity'] < low_stock_threshold else row['name']
        table_data.append([row['id'], name, row['quantity']])
    table = Table(table_data)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12), ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ])
    table.setStyle(style)
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return buffer

# --- Interfaz de Streamlit ---
st.set_page_config(page_title="Gestor de Inventarios", layout="wide", page_icon="📦")
manager = InventoryManager()

st.title("📦 Gestor de Inventario Pro X")

# --- Pestañas Principales ---
tab_main, tab_about = st.tabs(["⚙️ Gestor Principal", "ℹ️ Acerca de"])

with tab_main:
    col_inventory, col_orders, col_report = st.columns(3, gap="large")

    with col_inventory:
        st.header("Inventario Actual", divider="blue")
        with st.expander("➕ Agregar/Actualizar Item"):
            with st.form("inventory_form", clear_on_submit=True):
                new_item_name = st.text_input("Nombre del Ingrediente")
                new_item_qty = st.number_input("Cantidad a Agregar", min_value=1, step=1)
                if st.form_submit_button("Agregar al Inventario", type="primary", use_container_width=True):
                    manager.add_inventory_item(new_item_name, new_item_qty)
        
        inventory_data = manager.get_inventory()
        st.dataframe(inventory_data, use_container_width=True, hide_index=True,
                      column_config={"quantity": st.column_config.NumberColumn("Cantidad", format="%d und")})
        
        pdf_buffer = generate_inventory_pdf(inventory_data, manager.LOW_STOCK_THRESHOLD)
        st.download_button("📄 Descargar Inventario en PDF", pdf_buffer, f"inventario_{datetime.now().strftime('%Y%m%d')}.pdf", "application/pdf", use_container_width=True)

    with col_orders:
        st.header("Gestión de Pedidos", divider="green")
        with st.expander("📝 Crear Nuevo Pedido", expanded=True):
            st.markdown("**Ingredientes Requeridos**")
            if 'order_ingredients' not in st.session_state: st.session_state.order_ingredients = [{'name': '', 'quantity': 1}]
            inventory_names = [""] + list(inventory_data['name'])
            for i, ing in enumerate(st.session_state.order_ingredients):
                c1, c2, c3 = st.columns([3, 1, 1])
                ing['name'] = c1.selectbox(f"Ingrediente {i+1}", inventory_names, key=f"ing_name_{i}", index=inventory_names.index(ing['name']) if ing['name'] in inventory_names else 0)
                ing['quantity'] = c2.number_input("Cant.", min_value=1, step=1, key=f"ing_qty_{i}", value=ing['quantity'])
                if c3.button("➖", key=f"del_ing_{i}"):
                    st.session_state.order_ingredients.pop(i)
                    st.rerun()
            if st.button("Añadir Ingrediente", use_container_width=True):
                st.session_state.order_ingredients.append({'name': '', 'quantity': 1})
                st.rerun()
            
            with st.form("order_form", clear_on_submit=True):
                order_title = st.text_input("Título del Pedido (ej: Plato del Día)")
                order_price = st.number_input("Precio de Venta ($)", min_value=0.01, format="%.2f")
                if st.form_submit_button("Crear Pedido", type="primary", use_container_width=True):
                    valid_ingredients = [ing for ing in st.session_state.order_ingredients if ing['name']]
                    if manager.create_order(order_title, order_price, valid_ingredients):
                        st.session_state.order_ingredients = [{'name': '', 'quantity': 1}]
                        st.rerun()

        tab_processing, tab_completed = st.tabs(["En Proceso", "Historial"])
        with tab_processing:
            processing_orders = st.session_state.orders_df[st.session_state.orders_df['status'] == 'processing']
            if processing_orders.empty: st.info("No hay pedidos en proceso.")
            else:
                for _, order in processing_orders.iterrows():
                    with st.container(border=True):
                        st.subheader(f"{order['title']} - ${order['price']:.2f}")
                        st.caption(f"Ingredientes: {', '.join([f'{ing['name']} (x{ing['quantity']})' for ing in order['ingredients']])}")
                        b1, b2 = st.columns(2)
                        if b1.button("✅ Completar", key=f"complete_{order['id']}", type="primary", use_container_width=True):
                            manager.complete_order(order['id']); st.rerun()
                        if b2.button("❌ Cancelar", key=f"cancel_{order['id']}", use_container_width=True):
                            manager.cancel_order(order['id']); st.rerun()
        with tab_completed:
            completed_orders = st.session_state.orders_df[st.session_state.orders_df['status'] == 'completed']
            if completed_orders.empty: st.info("No hay pedidos en el historial.")
            else: st.dataframe(completed_orders[['id', 'title', 'price']].rename(columns={'title': 'Título', 'price': 'Precio'}), use_container_width=True, hide_index=True)

    with col_report:
        st.header("Informe Financiero", divider="violet")
        report_data = manager.get_report()
        st.metric("💰 Total Ventas (Pedidos Completados)", f"${report_data['total_sales']:.2f}")
        st.subheader("Resumen de Inventario Final")
        st.dataframe(report_data['final_inventory'][['name', 'quantity']].rename(columns={'name': 'Item', 'quantity': 'Stock'}), use_container_width=True, hide_index=True)

with tab_about:
    with st.container(border=True):
        st.header("Sobre el Autor y la Aplicación")
        _, center_col, _ = st.columns([1, 1, 1])
        with center_col:
            st.image("https://placehold.co/250x250/2B3137/FFFFFF?text=J.S.", width=250, caption="Joseph Javier Sánchez Acuña")
        st.title("Joseph Javier Sánchez Acuña")
        st.subheader("_Ingeniero Industrial, Experto en Inteligencia Artificial y Desarrollo de Software._")
        st.markdown("---")
        st.subheader("Acerca de esta Herramienta")
        st.markdown("""
        Esta aplicación de **Gestión de Inventarios y Pedidos** fue creada para ofrecer una solución sencilla pero potente para pequeños negocios o proyectos. Permite un control en tiempo real del stock, la creación de pedidos que descuentan automáticamente los ingredientes, y la visualización de un informe financiero básico.
        
        El objetivo es demostrar cómo herramientas como Streamlit pueden ser utilizadas para construir aplicaciones de gestión funcionales rápidamente, facilitando la toma de decisiones basada en datos.
        """)
        st.markdown("---")
        st.subheader("Contacto y Enlaces Profesionales")
        st.markdown(
            """
            - 🔗 **LinkedIn:** [joseph-javier-sánchez-acuña](https://www.linkedin.com/in/joseph-javier-sánchez-acuña-150410275)
            - 📂 **GitHub:** [GIUSEPPESAN21](https://github.com/GIUSEPPESAN21)
            - 📧 **Email:** [joseph.sanchez@uniminuto.edu.co](mailto:joseph.sanchez@uniminuto.edu.co)
            """
        )

