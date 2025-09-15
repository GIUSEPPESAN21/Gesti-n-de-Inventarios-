# -*- coding: utf-8 -*-
"""
Aplicación Streamlit para la Gestión de Inventarios y Pedidos.

Esta aplicación es una adaptación de un sistema originalmente construido con Flask y HTML/JavaScript.
Proporciona una interfaz interactiva para gestionar un inventario, procesar pedidos
y generar informes financieros, todo dentro de un único script de Python.
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

        # Normalizar para evitar duplicados (ej: 'arroz' y 'Arroz')
        normalized_name = name.lower()
        existing_items = st.session_state.inventory_df[st.session_state.inventory_df['name'].str.lower() == normalized_name]

        if not existing_items.empty:
            # El item existe, actualizar cantidad
            idx = existing_items.index[0]
            st.session_state.inventory_df.loc[idx, 'quantity'] += quantity
            st.toast(f"Stock de '{name}' actualizado.", icon="📦")
        else:
            # Nuevo item
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
            'ingredients': ingredients, # Lista de dicts
            'status': 'processing'
        }])
        st.session_state.orders_df = pd.concat([st.session_state.orders_df, new_order], ignore_index=True)
        st.session_state.next_order_id += 1
        st.toast(f"Pedido '{title}' creado exitosamente.", icon="🧾")
        # Aquí se podrían integrar notificaciones de Twilio si se configuran los secrets
        return True

    def complete_order(self, order_id):
        order_idx = st.session_state.orders_df[st.session_state.orders_df['id'] == order_id].index
        if order_idx.empty:
            st.error(f"No se encontró el pedido con ID {order_id}.")
            return

        order = st.session_state.orders_df.loc[order_idx[0]]
        
        # 1. Verificar si hay stock suficiente
        missing_items = []
        for ing in order['ingredients']:
            item_name_lower = ing['name'].lower()
            inv_item_series = st.session_state.inventory_df[st.session_state.inventory_df['name'].str.lower() == item_name_lower]
            if inv_item_series.empty or inv_item_series.iloc[0]['quantity'] < ing['quantity']:
                current_qty = 0 if inv_item_series.empty else inv_item_series.iloc[0]['quantity']
                missing_items.append(f"{ing['name']} (necesita {ing['quantity']}, disponible {current_qty})")

        if missing_items:
            st.warning(f"Stock insuficiente para completar el pedido '{order['title']}': {', '.join(missing_items)}")
            return

        # 2. Deducir del inventario
        low_stock_alerts = []
        for ing in order['ingredients']:
            item_name_lower = ing['name'].lower()
            inv_idx = st.session_state.inventory_df[st.session_state.inventory_df['name'].str.lower() == item_name_lower].index[0]
            st.session_state.inventory_df.loc[inv_idx, 'quantity'] -= ing['quantity']
            
            # Verificar si el stock quedó bajo
            new_qty = st.session_state.inventory_df.loc[inv_idx, 'quantity']
            if new_qty < self.LOW_STOCK_THRESHOLD:
                low_stock_alerts.append(f"{st.session_state.inventory_df.loc[inv_idx, 'name']}: {new_qty} restantes")

        # 3. Actualizar estado del pedido
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
        return {
            'total_sales': total_sales,
            'final_inventory': final_inventory
        }

# --- Funciones de Generación de PDF ---

def generate_inventory_pdf(inventory_df, low_stock_threshold):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Reporte de Inventario", styles['h1']))
    story.append(Paragraph(f"Generado el: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    story.append(Spacer(1, 0.2 * inch))

    table_data = [['ID', 'Nombre', 'Cantidad']]
    for _, row in inventory_df.iterrows():
        # Marcar items con bajo stock
        name = row['name']
        if row['quantity'] < low_stock_threshold:
            name = f"⚠️ {name} (Bajo Stock!)"
        table_data.append([row['id'], name, row['quantity']])

    table = Table(table_data)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
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
st.markdown("Una herramienta interactiva para la gestión de inventario y pedidos en tiempo real.")

# --- Columnas principales de la UI ---
col_inventory, col_orders, col_report = st.columns(3, gap="large")

# --- Columna 1: Inventario ---
with col_inventory:
    st.header("Inventario Actual", divider="blue")
    
    # Formulario para agregar items
    with st.expander("➕ Agregar/Actualizar Item", expanded=False):
        with st.form("inventory_form", clear_on_submit=True):
            new_item_name = st.text_input("Nombre del Ingrediente")
            new_item_qty = st.number_input("Cantidad a Agregar", min_value=1, step=1)
            submitted = st.form_submit_button("Agregar al Inventario", type="primary", use_container_width=True)
            if submitted:
                manager.add_inventory_item(new_item_name, new_item_qty)

    # Mostrar inventario
    inventory_data = manager.get_inventory()
    st.dataframe(
        inventory_data,
        use_container_width=True,
        hide_index=True,
        column_config={
            "quantity": st.column_config.NumberColumn(
                "Cantidad",
                help="Stock actual del item.",
                format="%d und"
            )
        }
    )

    # Botón de descarga de PDF
    pdf_buffer = generate_inventory_pdf(inventory_data, manager.LOW_STOCK_THRESHOLD)
    st.download_button(
        label="📄 Descargar Inventario en PDF",
        data=pdf_buffer,
        file_name=f"inventario_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
        use_container_width=True
    )

# --- Columna 2: Pedidos ---
with col_orders:
    st.header("Gestión de Pedidos", divider="green")

    with st.expander("📝 Crear Nuevo Pedido", expanded=True):
        with st.form("order_form", clear_on_submit=True):
            order_title = st.text_input("Título del Pedido (ej: Plato del Día)")
            order_price = st.number_input("Precio de Venta ($)", min_value=0.01, format="%.2f")
            
            st.markdown("**Ingredientes Requeridos**")
            # Ingredientes dinámicos
            if 'order_ingredients' not in st.session_state:
                st.session_state.order_ingredients = [{'name': '', 'quantity': 1}]

            inventory_names = [""] + list(inventory_data['name'])
            
            for i, ing in enumerate(st.session_state.order_ingredients):
                c1, c2, c3 = st.columns([3, 1, 1])
                ing['name'] = c1.selectbox(f"Ingrediente {i+1}", inventory_names, key=f"ing_name_{i}")
                ing['quantity'] = c2.number_input("Cant.", min_value=1, step=1, key=f"ing_qty_{i}")
                if c3.button("➖", key=f"del_ing_{i}"):
                    st.session_state.order_ingredients.pop(i)
                    st.rerun()

            if st.button("Añadir Ingrediente", use_container_width=True):
                st.session_state.order_ingredients.append({'name': '', 'quantity': 1})
                st.rerun()

            submit_order = st.form_submit_button("Crear Pedido", type="primary", use_container_width=True)
            if submit_order:
                # Filtrar ingredientes vacíos antes de crear el pedido
                valid_ingredients = [ing for ing in st.session_state.order_ingredients if ing['name']]
                if manager.create_order(order_title, order_price, valid_ingredients):
                    st.session_state.order_ingredients = [{'name': '', 'quantity': 1}] # Reset

    # Pestañas para pedidos en proceso y completados
    tab_processing, tab_completed = st.tabs(["En Proceso", "Historial (Completados)"])
    
    with tab_processing:
        processing_orders = st.session_state.orders_df[st.session_state.orders_df['status'] == 'processing']
        if processing_orders.empty:
            st.info("No hay pedidos en proceso.")
        else:
            for _, order in processing_orders.iterrows():
                with st.container(border=True):
                    st.subheader(f"{order['title']} - ${order['price']:.2f}")
                    ingredients_str = ", ".join([f"{ing['name']} (x{ing['quantity']})" for ing in order['ingredients']])
                    st.caption(f"Ingredientes: {ingredients_str}")
                    
                    b1, b2 = st.columns(2)
                    if b1.button("✅ Completar Pedido", key=f"complete_{order['id']}", type="primary", use_container_width=True):
                        manager.complete_order(order['id'])
                        st.rerun()
                    if b2.button("❌ Cancelar Pedido", key=f"cancel_{order['id']}", use_container_width=True):
                        manager.cancel_order(order['id'])
                        st.rerun()

    with tab_completed:
        completed_orders = st.session_state.orders_df[st.session_state.orders_df['status'] == 'completed']
        if completed_orders.empty:
            st.info("No hay pedidos en el historial.")
        else:
             st.dataframe(
                completed_orders[['id', 'title', 'price']].rename(columns={'title': 'Título', 'price': 'Precio'}),
                use_container_width=True,
                hide_index=True
             )

# --- Columna 3: Informe Financiero ---
with col_report:
    st.header("Informe Financiero", divider="violet")
    
    report_data = manager.get_report()
    
    st.metric(
        label="💰 Total Ventas (Pedidos Completados)",
        value=f"${report_data['total_sales']:.2f}",
        help="Suma de los precios de todos los pedidos marcados como completados."
    )
    
    st.subheader("Resumen de Inventario Final")
    final_inventory_display = report_data['final_inventory'][['name', 'quantity']]
    st.dataframe(final_inventory_display.rename(columns={'name': 'Item', 'quantity': 'Stock Actual'}), use_container_width=True, hide_index=True)

