# Import necessary libraries from Flask
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import copy
import os
from twilio.rest import Client # Import the Twilio Client
import logging # Recommended for better logging

# Initialize the Flask application
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, template_folder=basedir)
CORS(app)

# --- Configuración de Twilio (Credenciales Directas como proporcionaste) ---
# !! ADVERTENCIA DE SEGURIDAD CRÍTICA !!
# Estos son los valores que proporcionaste. ASEGÚRATE de que
# TWILIO_ACCOUNT_SID y TWILIO_AUTH_TOKEN sean TUS CREDENCIALES REALES
# de tu cuenta de Twilio, y no placeholders o ejemplos.
# El SID "ACe6fc..." es un SID de ejemplo común de Twilio.
# Si usas credenciales de ejemplo, NO FUNCIONARÁ.
TWILIO_ACCOUNT_SID = "ACe6fc51bff702ab5a8ddd10dd956a5313"
TWILIO_AUTH_TOKEN = "63d61de04e845e01a3ead4d8f941fcdd"
TWILIO_WHATSAPP_NUMBER = "+14155238886" # Número de la Sandbox de Twilio
DESTINATION_WHATSAPP_NUMBER = "+573222074527" # Tu número personal de WhatsApp

LOW_STOCK_THRESHOLD = 10

# Initialize Twilio Client
twilio_client = None
print("--- DEBUGGING TWILIO CONFIG ---")
print(f"TWILIO_ACCOUNT_SID: {TWILIO_ACCOUNT_SID}")
print(f"TWILIO_AUTH_TOKEN: {'*' * (len(TWILIO_AUTH_TOKEN) - 4) + TWILIO_AUTH_TOKEN[-4:] if TWILIO_AUTH_TOKEN else 'NO CONFIGURADO'}") # No mostrar el token completo en logs públicos
print(f"TWILIO_WHATSAPP_NUMBER: {TWILIO_WHATSAPP_NUMBER}")
print(f"DESTINATION_WHATSAPP_NUMBER: {DESTINATION_WHATSAPP_NUMBER}")

if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_NUMBER and DESTINATION_WHATSAPP_NUMBER:
    # Verifica si el SID o el Token parecen ser los placeholders de ejemplo
    if TWILIO_ACCOUNT_SID == "ACe6fc51bff702ab5a8ddd10dd956a5313":
        print("ADVERTENCIA: TWILIO_ACCOUNT_SID parece ser un valor de placeholder/ejemplo.")
    if TWILIO_AUTH_TOKEN == "63d61de04e845e01a3ead4d8f941fcdd": # Compara con el placeholder que usaste
        print("ADVERTENCIA: TWILIO_AUTH_TOKEN parece ser un valor de placeholder/ejemplo.")

    try:
        print("Intentando inicializar el cliente de Twilio...")
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        print("Cliente de Twilio INICIALIZADO EXITOSAMENTE.")
        # Puedes hacer una pequeña prueba aquí si quieres, como listar números (con cuidado de no incurrir en costos)
        # por ejemplo: numbers = twilio_client.incoming_phone_numbers.list(limit=1)
        # print(f"Prueba de cliente: {numbers}")
    except Exception as e:
        print(f"ERROR CRÍTICO: Falló la inicialización del cliente de Twilio: {e}")
        twilio_client = None # Asegurarse de que esté None si falla
else:
    print("ERROR: Faltan una o más credenciales/números de Twilio. Las alertas de WhatsApp NO funcionarán.")
print("--- FIN DEBUGGING TWILIO CONFIG ---")


# --- In-Memory Data Storage ---
initial_inventory_data = [
    {'id': 1, 'name': 'Camaron', 'quantity': 10, 'original_name': 'Camaron'},
    {'id': 2, 'name': 'Mojarra', 'quantity': 8, 'original_name': 'Mojarra'},
    {'id': 3, 'name': 'Arroz', 'quantity': 500, 'original_name': 'Arroz'},
    {'id': 4, 'name': 'Cebolla', 'quantity': 5, 'original_name': 'Cebolla'}
]
inventory = {item['name'].lower(): {'id': item['id'], 'name': item['original_name'], 'quantity': item['quantity']} for item in initial_inventory_data}
orders = {}
next_inventory_id = max(item['id'] for item in inventory.values()) + 1 if inventory else 1
next_order_id = 1

# --- Helper Functions ---
def find_inventory_item_by_normalized_name(normalized_name):
    return inventory.get(normalized_name)
def find_order_by_id(order_id):
    return orders.get(order_id)

# --- WhatsApp Alert Function (Twilio) ---
def enviar_alerta_twilio_whatsapp(mensaje):
    print(f"DEBUG: Se llamó a enviar_alerta_twilio_whatsapp con mensaje: '{mensaje}'")
    if not twilio_client:
        print("ERROR ALERTA: Cliente de Twilio NO inicializado. No se puede enviar mensaje.")
        # app.logger.error("ALERT ERROR: Twilio client not initialized.") # Si usas app.logger
        return False
    
    # Validaciones adicionales de los números (aunque ya se hicieron arriba)
    if not TWILIO_WHATSAPP_NUMBER or not TWILIO_WHATSAPP_NUMBER.startswith('+'):
        print(f"ERROR ALERTA: TWILIO_WHATSAPP_NUMBER ('{TWILIO_WHATSAPP_NUMBER}') no es válido o no está configurado.")
        return False
    if not DESTINATION_WHATSAPP_NUMBER or not DESTINATION_WHATSAPP_NUMBER.startswith('+'):
        print(f"ERROR ALERTA: DESTINATION_WHATSAPP_NUMBER ('{DESTINATION_WHATSAPP_NUMBER}') no es válido o no está configurado.")
        return False

    try:
        from_whatsapp_number = f'whatsapp:{TWILIO_WHATSAPP_NUMBER}'
        to_whatsapp_number = f'whatsapp:{DESTINATION_WHATSAPP_NUMBER}'

        print(f"INFO ALERTA: Intentando enviar mensaje WhatsApp via Twilio a {to_whatsapp_number} desde {from_whatsapp_number}...")
        message = twilio_client.messages.create(
            from_=from_whatsapp_number,
            body=mensaje,
            to=to_whatsapp_number
        )
        print(f"INFO ALERTA: Mensaje Twilio enviado/encolado. SID: {message.sid}, Estado: {message.status}, Precio: {message.price}, URI: {message.uri}")
        if message.error_code:
            print(f"ERROR ALERTA TWILIO: Código de Error: {message.error_code}, Mensaje de Error: {message.error_message}")
        return True
    except Exception as e:
        print(f"ERROR ALERTA CRÍTICO: Excepción al enviar mensaje con Twilio: {e}")
        if hasattr(e, 'status'): print(f"DEBUG ALERTA: Twilio Error Status HTTP: {e.status}")
        if hasattr(e, 'code'): print(f"DEBUG ALERTA: Twilio Error Code API: {e.code}") # Este es el código de error de Twilio
        if hasattr(e, 'more_info'): print(f"DEBUG ALERTA: Twilio More Info: {e.more_info}")
        return False

# --- API Endpoints ---
@app.route('/')
def index_page():
    try:
        return render_template('index.html')
    except Exception as e:
        print(f"Error rendering template: {e}") # Usar print para asegurar visibilidad en consola
        return "Error loading page. Template not found or other server error.", 500

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    inventory_list = sorted(list(inventory.values()), key=lambda item: item['name'])
    return jsonify(inventory_list)

@app.route('/api/inventory', methods=['POST'])
def add_inventory_item():
    global next_inventory_id, inventory
    data = request.get_json()
    if not data or 'name' not in data or 'quantity' not in data:
        return jsonify({'error': 'Faltan nombre o cantidad.'}), 400
    name = data['name'].strip()
    normalized_name = name.lower()
    if not name: return jsonify({'error': 'El nombre del item no puede estar vacío.'}), 400
    try:
        quantity_to_add = int(data['quantity'])
        if quantity_to_add <= 0: return jsonify({'error': 'La cantidad debe ser un entero positivo.'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Cantidad inválida, debe ser un entero positivo.'}), 400
    existing_item = inventory.get(normalized_name)
    if existing_item:
        existing_item['quantity'] += quantity_to_add
        print(f"Inventario actualizado: {existing_item['name']} ahora tiene {existing_item['quantity']}")
        return jsonify(existing_item), 200
    else:
        new_item_data = {'id': next_inventory_id, 'name': name, 'quantity': quantity_to_add}
        inventory[normalized_name] = new_item_data
        next_inventory_id += 1
        print(f"Nuevo item agregado: {name} con {quantity_to_add} unidades")
        return jsonify(new_item_data), 201

@app.route('/api/orders', methods=['GET'])
def get_orders():
    status_filter = request.args.get('status')
    all_orders_list = list(orders.values())
    if status_filter:
        filtered_orders = [order for order in all_orders_list if order['status'] == status_filter]
        return jsonify(sorted(filtered_orders, key=lambda o: o['id'], reverse=True))
    return jsonify(sorted(all_orders_list, key=lambda o: o['id'], reverse=True))

@app.route('/api/orders', methods=['POST'])
def create_order():
    global next_order_id, orders
    data = request.get_json()
    required_fields = ['title', 'price', 'ingredients']
    if not data or not all(k in data for k in required_fields):
        return jsonify({'error': 'Faltan campos requeridos para el pedido (título, precio, ingredientes).'}), 400
    title = data['title'].strip()
    if not title: return jsonify({'error': 'El título del pedido no puede estar vacío.'}), 400
    try:
        price = float(data['price'])
        if price < 0: return jsonify({'error': 'El precio no puede ser negativo.'}), 400
    except (ValueError, TypeError): return jsonify({'error': 'Formato de precio inválido.'}), 400
    if not isinstance(data['ingredients'], list) or not data['ingredients']:
         return jsonify({'error': 'Los ingredientes deben ser una lista no vacía.'}), 400
    validated_ingredients = []
    for ing_data in data['ingredients']:
        if not isinstance(ing_data, dict) or not all(k in ing_data for k in ('name', 'quantity')):
            return jsonify({'error': 'Formato de ingrediente inválido. Cada uno debe tener nombre y cantidad.'}), 400
        ing_name = ing_data['name'].strip()
        if not ing_name: return jsonify({'error': 'Nombre de ingrediente inválido (no puede estar vacío).'}), 400
        try:
            ing_quantity = int(ing_data['quantity'])
            if ing_quantity <= 0: return jsonify({'error': f"Cantidad inválida para ingrediente '{ing_name}'. Debe ser positiva."}), 400
        except (ValueError, TypeError):
             return jsonify({'error': f"Cantidad inválida para ingrediente '{ing_name}'. Debe ser un entero."}), 400
        validated_ingredients.append({'name': ing_name, 'quantity': ing_quantity})
    new_order_id = next_order_id
    new_order = {'id': new_order_id, 'title': title, 'price': price, 'ingredients': validated_ingredients, 'status': 'processing'}
    orders[new_order_id] = new_order
    next_order_id += 1
    print(f"Nuevo pedido creado: #{new_order['id']} - {new_order['title']}")
    return jsonify(new_order), 201

@app.route('/api/orders/<int:order_id>/complete', methods=['PUT'])
def complete_order_api(order_id):
    global inventory
    order = find_order_by_id(order_id)
    if not order: return jsonify({'error': 'Pedido no encontrado.'}), 404
    if order['status'] == 'completed': return jsonify({'message': 'El pedido ya está completado.'}), 200
    temp_inventory_snapshot = copy.deepcopy(inventory)
    missing_items_details = []
    items_to_deduct_from_actual_inventory = []
    for req_ingredient in order['ingredients']:
        req_name_normalized = req_ingredient['name'].lower()
        try:
            required_quantity = int(req_ingredient['quantity'])
            if required_quantity <= 0: return jsonify({'error': f"Cantidad inválida para ingrediente '{req_ingredient.get('name', 'N/A')}' (debe ser > 0)."}), 400
        except (ValueError, TypeError, KeyError):
             return jsonify({'error': f"Cantidad inválida para ingrediente '{req_ingredient.get('name', 'N/A')}'."}), 400
        inv_item_temp = temp_inventory_snapshot.get(req_name_normalized)
        if inv_item_temp:
            if inv_item_temp['quantity'] >= required_quantity:
                inv_item_temp['quantity'] -= required_quantity
                items_to_deduct_from_actual_inventory.append({'normalized_name': req_name_normalized, 'quantity': required_quantity, 'original_name': inv_item_temp['name']})
            else:
                missing_items_details.append(f"{inv_item_temp['name']} (necesita {required_quantity}, disponible {inv_item_temp['quantity']})")
        else:
            missing_items_details.append(f"{req_ingredient['name']} (no encontrado en inventario)")
    if missing_items_details:
        error_message = f"Inventario insuficiente para pedido #{order_id} ('{order['title']}')"
        missing_str = "\n- ".join(missing_items_details)
        print(f"ERROR: {error_message}. Faltantes: {missing_str}")
        alerta_stock_insuficiente = f"⚠️ ALERTA STOCK (App) ⚠️\nFallo al completar pedido #{order_id} ('{order['title']}').\nInventario insuficiente:\n- {missing_str}\nRevisar inventario urgentemente."
        enviar_alerta_twilio_whatsapp(alerta_stock_insuficiente) # Intenta enviar alerta incluso si falla el pedido
        return jsonify({'error': error_message, 'missing': missing_items_details}), 400
    low_stock_items_after_deduction = []
    for item_deduction in items_to_deduct_from_actual_inventory:
        inv_item_actual = inventory.get(item_deduction['normalized_name'])
        if inv_item_actual:
            inv_item_actual['quantity'] -= item_deduction['quantity']
            print(f"Inventario deducido: {item_deduction['quantity']} de '{inv_item_actual['name']}'. Restante: {inv_item_actual['quantity']}")
            if inv_item_actual['quantity'] < LOW_STOCK_THRESHOLD:
                low_stock_items_after_deduction.append(f"- {inv_item_actual['name']}: {inv_item_actual['quantity']} unidades (Umbral: {LOW_STOCK_THRESHOLD})")
    order['status'] = 'completed'
    print(f"Pedido completado: #{order_id} - {order['title']}")
    mensaje_completado = f"✅ PEDIDO COMPLETADO (App) ✅\nPedido #{order_id} ('{order['title']}') marcado como completado.\nPrecio: ${order['price']:.2f}"
    enviar_alerta_twilio_whatsapp(mensaje_completado)
    if low_stock_items_after_deduction:
        low_stock_str = "\n".join(low_stock_items_after_deduction)
        mensaje_bajo_stock = f"📉 ALERTA BAJO STOCK (App) 📉\nItems con nivel bajo después del pedido #{order_id}:\n{low_stock_str}"
        enviar_alerta_twilio_whatsapp(mensaje_bajo_stock)
    return jsonify(order), 200

@app.route('/api/orders/<int:order_id>', methods=['DELETE'])
def cancel_order_api(order_id):
    global orders
    order_to_delete = find_order_by_id(order_id)
    if not order_to_delete: return jsonify({'error': 'Pedido no encontrado.'}), 404
    del orders[order_id]
    print(f"Pedido cancelado/eliminado: #{order_id} - {order_to_delete.get('title', 'N/A')}")
    return jsonify({'message': 'Pedido eliminado exitosamente.'}), 200

@app.route('/api/report', methods=['GET'])
def get_report():
    total_sales = sum(order_item['price'] for order_item in orders.values() if order_item['status'] == 'completed')
    final_inventory_report = sorted(list(inventory.values()), key=lambda item: item['name'])
    return jsonify({'total_sales': total_sales, 'final_inventory': final_inventory_report, 'low_stock_threshold': LOW_STOCK_THRESHOLD})

# --- Run the Flask App ---
if __name__ == '__main__':
    # No usar app.logger aquí porque puede no estar configurado aún si Flask no ha iniciado completamente
    # Los prints para la configuración de Twilio ya están arriba.
    print("Iniciando la aplicación Flask...")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False) # use_reloader=False para evitar doble inicialización de prints