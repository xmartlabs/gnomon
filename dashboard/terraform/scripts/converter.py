import json
import os

# Utilice este script para convertir archivos .env al formato de ECS (json)

def env_to_json(env_file_path, json_file_path):
    # Verificar si el archivo .env existe
    if not os.path.exists(env_file_path):
        print(f"El archivo {env_file_path} no existe.")
        return

    # Leer el archivo .env y cargar las variables de entorno
    with open(env_file_path, 'r') as env_file:
        env_lines = env_file.readlines()

    # Crear una lista de diccionarios para almacenar las variables
    env_list = []
    for line in env_lines:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            
            # Conservar el valor tal como está si es cadena vacía entre comillas
            value = value if value != '""' else ""
            
            env_list.append({"name": key, "value": value})

    # Escribir la lista de diccionarios en formato JSON
    with open(json_file_path, 'w') as json_file:
        json.dump(env_list, json_file, indent=2)

    print(f"Se ha creado el archivo JSON: {json_file_path}")

# Definir ruta de archivos origen y destino:
env_file_path = '.env.example'
json_file_path = 'variables.json'
env_to_json(env_file_path, json_file_path)


