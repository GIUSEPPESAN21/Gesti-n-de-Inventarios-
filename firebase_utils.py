import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
import logging
from datetime import datetime
import streamlit as st

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FirebaseManager:
    def __init__(self):
        self.db = None
        self.project_id = "reconocimiento-inventario"
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Inicializa Firebase usando Streamlit secrets de forma segura."""
        try:
            if not firebase_admin._apps:
                creds_base64 = st.secrets.get('FIREBASE_SERVICE_ACCOUNT_BASE64')
                if not creds_base64:
                    raise ValueError("El secret 'FIREBASE_SERVICE_ACCOUNT_BASE64' no fue encontrado.")
                
                creds_json_str = base64.b64decode(creds_base64).decode('utf-8')
                creds_dict = json.loads(creds_json_str)
                
                cred = credentials.Certificate(creds_dict)
                firebase_admin.initialize_app(cred, {'projectId': self.project_id})
                logger.info("Firebase inicializado correctamente.")
            
            self.db = firestore.client()
        except Exception as e:
            logger.error(f"Error fatal al inicializar Firebase: {e}")
            raise

    # --- Métodos para Inventario ---
    def save_inventory_item(self, data, custom_id):
        try:
            doc_ref = self.db.collection('inventory').document(custom_id)
            data['timestamp'] = datetime.now().isoformat()
            doc_ref.set(data, merge=True)
            logger.info(f"Elemento de inventario guardado/actualizado: {custom_id}")
        except Exception as e:
            logger.error(f"Error al guardar en 'inventory': {e}")
            raise

    def get_all_inventory_items(self):
        try:
            docs = self.db.collection('inventory').stream()
            items = []
            for doc in docs:
                item = doc.to_dict()
                item['id'] = doc.id
                items.append(item)
            return items
        except Exception as e:
            logger.error(f"Error al obtener de 'inventory': {e}")
            return []

    def delete_inventory_item(self, doc_id):
        try:
            self.db.collection('inventory').document(doc_id).delete()
            logger.info(f"Elemento de inventario {doc_id} eliminado.")
        except Exception as e:
            logger.error(f"Error al eliminar de 'inventory': {e}")
            raise

    # --- Métodos para Pedidos ---
    def create_order(self, order_data):
        try:
            order_data['timestamp'] = datetime.now().isoformat()
            self.db.collection('orders').add(order_data)
            logger.info("Nuevo pedido creado.")
        except Exception as e:
            logger.error(f"Error al crear pedido: {e}")
            raise

    def get_orders(self, status='processing'):
        try:
            query = self.db.collection('orders')
            if status:
                query = query.where(filter=firestore.FieldFilter('status', '==', status))
            
            docs = query.stream()
            orders = []
            for doc in docs:
                order = doc.to_dict()
                order['id'] = doc.id
                orders.append(order)
            return orders
        except Exception as e:
            logger.error(f"Error al obtener pedidos: {e}")
            return []

    def cancel_order(self, order_id):
        try:
            self.db.collection('orders').document(order_id).delete()
            logger.info(f"Pedido {order_id} cancelado.")
        except Exception as e:
            logger.error(f"Error al cancelar pedido: {e}")
            raise

    # CORRECCIÓN DEFINITIVA: Se usa el decorador en un único método público.
    # La app llamará a `firebase.complete_order(order_id)` y el decorador
    # se encargará de crear y pasar el objeto 'transaction'.
    @firestore.transactional
    def complete_order(self, transaction, order_id):
        """
        Completa un pedido de forma atómica.
        """
        try:
            order_ref = self.db.collection('orders').document(order_id)
            order_snapshot = order_ref.get(transaction=transaction)
            if not order_snapshot.exists:
                return False, "El pedido no existe."
            
            order_data = order_snapshot.to_dict()
            
            inventory_updates = []
            for ing in order_data.get('ingredients', []):
                if 'id' not in ing:
                    return False, f"Dato inconsistente en el pedido: al ingrediente '{ing.get('name', 'desconocido')}' le falta su ID."

                item_ref = self.db.collection('inventory').document(ing['id'])
                item_snapshot = item_ref.get(transaction=transaction)
                
                if not item_snapshot.exists:
                    return False, f"Ingrediente con ID '{ing['id']}' no encontrado en el inventario."
                
                current_quantity = item_snapshot.to_dict().get('quantity', 0)
                if current_quantity < ing['quantity']:
                    return False, f"Stock insuficiente para '{ing.get('name', ing['id'])}'. Necesitas {ing['quantity']}, tienes {current_quantity}."
                
                new_quantity = current_quantity - ing['quantity']
                inventory_updates.append({'ref': item_ref, 'quantity': new_quantity})

            for update in inventory_updates:
                transaction.update(update['ref'], {'quantity': update['quantity']})
                
            transaction.update(order_ref, {'status': 'completed'})
            
            return True, f"Pedido '{order_data['title']}' completado con éxito."
        except Exception as e:
            logger.error(f"Fallo DENTRO de la transacción para el pedido {order_id}: {e}")
            # Al lanzar la excepción, Firebase se encarga de revertir la transacción.
            raise e

