# -*- coding: utf-8 -*-
"""
Aplicación de Tablero Kanban "Kankai" con Streamlit.

Versión 4.0: Se integran alertas de WhatsApp para tareas de alta
dificultad y se mantiene la pestaña "Acerca de".
"""
import streamlit as st
import pandas as pd
import time
import random
from io import BytesIO
import matplotlib.pyplot as plt

# --- Importaciones para Excel y Twilio ---
try:
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as ExcelImage
    from openpyxl.utils.dataframe import dataframe_to_rows
    IS_EXCEL_AVAILABLE = True
except ImportError:
    IS_EXCEL_AVAILABLE = False

try:
    from twilio.rest import Client
    from twilio.base.exceptions import TwilioRestException
    IS_TWILIO_AVAILABLE = True
except ImportError:
    IS_TWILIO_AVAILABLE = False
    Client, TwilioRestException = None, None

# --- Lógica de Negocio y Manejo de Datos ---

class TaskManager:
    """
    Clase para manejar la lógica de las tareas del tablero Kanban.
    """
    def __init__(self):
        if 'tasks_df' not in st.session_state:
            st.session_state.tasks_df = pd.DataFrame([
                {'id': 'task-1', 'name': 'Diseñar Prototipo Alfa', 'estimatedTimeMinutes': 480, 'difficulty': '2', 'status': 'todo'},
                {'id': 'task-2', 'name': 'Investigación de Mercado UX', 'estimatedTimeMinutes': 720, 'difficulty': '3', 'status': 'todo'},
                {'id': 'task-3', 'name': 'Reunión Kick-off Proyecto K', 'estimatedTimeMinutes': 60, 'difficulty': '1', 'status': 'inprogress'},
                {'id': 'task-4', 'name': 'Configurar Entorno Dev', 'estimatedTimeMinutes': 240, 'difficulty': '1', 'status': 'done'},
            ])
        if 'next_task_id' not in st.session_state:
            st.session_state.next_task_id = 5

        self.difficulty_map = {'1': 'Baja', '2': 'Media', '3': 'Alta'}
        self.status_map = {'todo': 'Por Hacer', 'inprogress': 'En Progreso', 'done': 'Finalizado'}
        self.difficulty_sort_order = {'1': 1, '2': 2, '3': 3}

    def get_tasks(self):
        return st.session_state.tasks_df

    def add_task(self, name, estimated_minutes, difficulty):
        name = name.strip()
        if not name or estimated_minutes <= 0:
            st.error("El nombre no puede estar vacío y el tiempo debe ser positivo.")
            return

        new_id = f"task-{st.session_state.next_task_id}"
        new_task = pd.DataFrame([{'id': new_id, 'name': name, 'estimatedTimeMinutes': estimated_minutes, 'difficulty': difficulty, 'status': 'todo'}])
        st.session_state.tasks_df = pd.concat([st.session_state.tasks_df, new_task], ignore_index=True)
        st.session_state.next_task_id += 1
        st.toast(f"Tarea '{name}' creada.", icon="📝")

        # --- Disparador de Alerta de WhatsApp ---
        if difficulty == '3': # '3' corresponde a Dificultad Alta
            mensaje = f"🚨 Tarea de Alta Dificultad Creada\n\n- **Nombre:** {name}\n- **Tiempo:** {format_minutes_to_hm(estimated_minutes)}"
            enviar_alerta_whatsapp(mensaje)

    def update_task_status(self, task_id, new_status):
        task_idx = st.session_state.tasks_df[st.session_state.tasks_df['id'] == task_id].index
        if not task_idx.empty:
            st.session_state.tasks_df.loc[task_idx, 'status'] = new_status
            task_name = st.session_state.tasks_df.loc[task_idx[0], 'name']
            st.toast(f"Tarea '{task_name}' movida a '{self.status_map[new_status]}'.", icon="🔄")

    def delete_task(self, task_id):
        task_name = st.session_state.tasks_df[st.session_state.tasks_df['id'] == task_id].iloc[0]['name']
        st.session_state.tasks_df = st.session_state.tasks_df[st.session_state.tasks_df['id'] != task_id]
        st.toast(f"Tarea '{task_name}' eliminada.", icon="🗑️")

    def get_progress_summary(self):
        df = st.session_state.tasks_df
        total_tasks = len(df)
        if total_tasks == 0: return {'done': 0, 'pending': 0, 'inprogress': 0, 'total': 0, 'percentage': 0}
        done_tasks = len(df[df['status'] == 'done'])
        inprogress_tasks = len(df[df['status'] == 'inprogress'])
        pending_tasks = total_tasks - done_tasks - inprogress_tasks
        percentage = round((done_tasks / total_tasks) * 100, 1) if total_tasks > 0 else 0
        return {'done': done_tasks, 'pending': pending_tasks, 'inprogress': inprogress_tasks, 'total': total_tasks, 'percentage': percentage}

# --- Lógica de Twilio ---
def inicializar_twilio_client():
    if not IS_TWILIO_AVAILABLE: return None
    try:
        if hasattr(st, 'secrets') and all(k in st.secrets for k in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"]):
            account_sid = st.secrets["TWILIO_ACCOUNT_SID"]
            auth_token = st.secrets["TWILIO_AUTH_TOKEN"]
            if account_sid.startswith("AC") and len(auth_token) > 30:
                st.session_state.twilio_configured = True
                return Client(account_sid, auth_token)
    except Exception: pass
    st.session_state.twilio_configured = False
    return None

def enviar_alerta_whatsapp(mensaje):
    if 'twilio_client' not in st.session_state or not st.session_state.twilio_client: return
    if not st.session_state.get('twilio_configured'):
        st.warning("Credenciales de Twilio no configuradas.", icon="⚠️")
        return
    try:
        from_number = st.secrets["TWILIO_WHATSAPP_FROM_NUMBER"]
        to_number = st.secrets["DESTINATION_WHATSAPP_NUMBER"]
        # Prefijo para cuentas de prueba
        mensaje_final = f"Your Twilio code is {random.randint(1000,9999)}\n\n{mensaje}"
        st.session_state.twilio_client.messages.create(from_=f'whatsapp:{from_number}', body=mensaje_final, to=f'whatsapp:{to_number}')
        st.toast(f"¡Alerta enviada a {to_number}!", icon="✅")
    except TwilioRestException as e:
        st.error(f"Error de Twilio: {e.msg}", icon="🚨")
        if e.code == 21608: st.warning("Reactiva tu Sandbox de WhatsApp.", icon="📱")
    except Exception as e:
        st.error(f"Error inesperado al enviar WhatsApp: {e}", icon="🚨")

# --- Funciones Auxiliares y de UI ---
def format_minutes_to_hm(minutes):
    if pd.isna(minutes) or minutes < 0: return "N/A"
    h = int(minutes // 60)
    m = int(minutes % 60)
    if h > 0 and m > 0: return f"{h}h {m}m"
    elif h > 0: return f"{h}h"
    else: return f"{m}m"

def create_progress_chart(summary):
    if summary['total'] == 0: return None
    labels = ['Finalizadas', 'En Progreso', 'Pendientes']
    sizes = [summary['done'], summary['inprogress'], summary['pending']]
    colors = ['#10b981', '#3b82f6', '#f59e0b']
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors, wedgeprops=dict(width=0.4, edgecolor='w'))
    ax.axis('equal')
    return fig

def generate_excel_report(tasks_df, summary, difficulty_map, status_map):
    if not IS_EXCEL_AVAILABLE: return None
    buffer = BytesIO()
    report_df = tasks_df.copy()
    report_df['estimatedTime'] = report_df['estimatedTimeMinutes'].apply(format_minutes_to_hm)
    report_df['difficulty'] = report_df['difficulty'].map(difficulty_map)
    report_df['status'] = report_df['status'].map(status_map)
    report_df = report_df[['id', 'name', 'status', 'difficulty', 'estimatedTime']]
    report_df.columns = ['ID', 'Nombre', 'Estado', 'Dificultad', 'Tiempo Estimado']
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        report_df.to_excel(writer, sheet_name='Tareas', index=False)
        fig = create_progress_chart(summary)
        if fig:
            img_buffer = BytesIO()
            fig.savefig(img_buffer, format='png')
            plt.close(fig)
            img_buffer.seek(0)
            ws = writer.sheets['Tareas']
            img = ExcelImage(img_buffer)
            img.anchor = f'A{len(report_df) + 3}'
            ws.add_image(img)
    buffer.seek(0)
    return buffer

# --- Interfaz de Streamlit ---
st.set_page_config(page_title="Kankai Pro", layout="wide", page_icon="📝")
manager = TaskManager()

if 'twilio_client' not in st.session_state:
    st.session_state.twilio_client = inicializar_twilio_client()

st.title("📝 Kankai Pro Dashboard")

# --- Navegación por Pestañas ---
tab_dashboard, tab_kanban, tab_manage, tab_about = st.tabs(["📊 Dashboard", "📋 Tablero Kanban", "⚙️ Gestión y Reportes", "ℹ️ Acerca de"])

with tab_dashboard:
    st.header("Análisis de Productividad")
    summary = manager.get_progress_summary()
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Tareas Totales", f"{summary['total']} 📝")
    kpi2.metric("Completadas", f"{summary['done']} ✅", f"{summary['percentage']}% del total")
    kpi3.metric("En Progreso", f"{summary['inprogress']} ⚙️")
    kpi4.metric("Pendientes", f"{summary['pending']} 📌")
    st.divider()
    chart1, chart2 = st.columns(2)
    with chart1:
        st.subheader("Progreso General")
        progress_chart = create_progress_chart(summary)
        if progress_chart: st.pyplot(progress_chart)
        else: st.info("No hay tareas para mostrar en el gráfico.")
    with chart2:
        st.subheader("Carga de Trabajo por Dificultad")
        tasks_df = manager.get_tasks()
        if not tasks_df.empty:
            difficulty_counts = tasks_df['difficulty'].map(manager.difficulty_map).value_counts()
            st.bar_chart(difficulty_counts)
        else: st.info("No hay tareas para analizar.")

with tab_kanban:
    st.header("Tablero de Tareas")
    col_todo, col_inprogress, col_done = st.columns(3, gap="medium")
    board_cols = {"todo": col_todo, "inprogress": col_inprogress, "done": col_done}
    tasks = manager.get_tasks()
    for status, col in board_cols.items():
        with col:
            st.subheader(f"{manager.status_map[status]} ({len(tasks[tasks['status'] == status])})", divider="gray")
            for _, task in tasks[tasks['status'] == status].iterrows():
                difficulty_color_map = {'1': 'green', '2': 'orange', '3': 'red'}
                color = difficulty_color_map.get(task['difficulty'], 'gray')
                with st.container(border=True):
                    st.markdown(f"**{task['name']}**")
                    st.caption(f"ID: {task['id']}")
                    st.markdown(f"🕒 **:blue[{format_minutes_to_hm(task['estimatedTimeMinutes'])}]** | Dificultad: **:{color}[{manager.difficulty_map.get(task['difficulty'], 'N/A')}]**")
                    btn_cols = st.columns(3)
                    if status == "todo":
                        if btn_cols[0].button("▶️ Iniciar", key=f"start_{task['id']}", use_container_width=True):
                            manager.update_task_status(task['id'], 'inprogress'); st.rerun()
                    if status == "inprogress":
                        if btn_cols[0].button("⏪", help="Devolver", key=f"return_{task['id']}", use_container_width=True):
                            manager.update_task_status(task['id'], 'todo'); st.rerun()
                        if btn_cols[2].button("✔️ Finalizar", key=f"finish_{task['id']}", type="primary", use_container_width=True):
                            manager.update_task_status(task['id'], 'done'); st.rerun()
                    if status == "done":
                        if btn_cols[0].button("🗑️", help="Eliminar", key=f"delete_{task['id']}", use_container_width=True):
                            manager.delete_task(task['id']); st.rerun()

with tab_manage:
    col_add, col_optimize = st.columns(2)
    with col_add:
        st.header("Añadir Nueva Tarea", divider="blue")
        with st.form("add_task_form", clear_on_submit=True, border=False):
            task_name = st.text_input("Nombre de la Tarea")
            c1, c2 = st.columns(2)
            task_hours = c1.number_input("Horas Estimadas", min_value=0, step=1)
            task_minutes = c2.number_input("Minutos", min_value=0, max_value=59, step=1)
            task_difficulty = st.selectbox("Dificultad", options=list(manager.difficulty_map.keys()), format_func=lambda x: manager.difficulty_map[x])
            if st.form_submit_button("Añadir Tarea", type="primary", use_container_width=True):
                total_minutes = (task_hours * 60) + task_minutes
                manager.add_task(task_name, total_minutes, task_difficulty)
    with col_optimize:
        st.header("Optimización y Reportes", divider="violet")
        st.subheader("Sugerencia de Orden")
        if st.button("💡 Generar Orden Sugerido", use_container_width=True):
            optimized_tasks = manager.get_optimization_suggestion()
            if optimized_tasks.empty: st.info("No hay tareas pendientes.")
            else:
                with st.expander("**Orden Sugerido**", expanded=True):
                    for i, (_, task) in enumerate(optimized_tasks.iterrows()):
                        st.markdown(f"{i+1}. **{task['name']}** ({manager.difficulty_map[task['difficulty']]}, {format_minutes_to_hm(task['estimatedTimeMinutes'])})")
        st.subheader("Descargar Reporte")
        excel_buffer = generate_excel_report(manager.get_tasks(), manager.get_progress_summary(), manager.difficulty_map, manager.status_map)
        st.download_button("📄 Descargar Reporte en Excel", excel_buffer, f"reporte_kankai_{time.strftime('%Y%m%d')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

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
        Esta aplicación de tablero **Kanban 'Kankai Pro'** fue creada para ofrecer una solución visual e interactiva para la gestión de tareas. El objetivo es aplicar los principios de la metodología Kanban para ayudar a individuos y equipos a organizar su flujo de trabajo, visualizar el progreso y optimizar la priorización de tareas.
        
        Desde la gestión de tareas en un tablero visual hasta el análisis de productividad y la exportación de reportes, cada funcionalidad está pensada para mejorar la eficiencia y la claridad en cualquier proyecto.
        """)
        st.markdown("---")
        st.subheader("Contacto y Enlaces Profesionales")
        st.markdown("""
            - 🔗 **LinkedIn:** [joseph-javier-sánchez-acuña](https://www.linkedin.com/in/joseph-javier-sánchez-acuña-150410275)
            - 📂 **GitHub:** [GIUSEPPESAN21](https://github.com/GIUSEPPESAN21)
            - 📧 **Email:** [joseph.sanchez@uniminuto.edu.co](mailto:joseph.sanchez@uniminuto.edu.co)
        """)

