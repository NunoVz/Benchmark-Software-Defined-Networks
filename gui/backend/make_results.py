# USAR PARA COMPILAR AS METRICAS DA LATENCIA

import os
import csv
import sys

files_c = ['onos']
files_t = ['3-tier','mesh']
files_m = ['northbound_api_latency.csv','southbound_NN_api_latency.csv', 'pppt_rtt.csv', 'rppt_rtt.csv', ]

file_names = []
for c in files_c:
    for t in files_t:
        for m in files_m:
            file_names.append(f"{c}_{t}_{m}")


# Lista de pastas
folders = ['traffic', 'DoS', 'slowloris', 'rest', 'malformed']

    
def find_info(file_name):
    avg_time_excl_max = None    
    results_avg_time_excl_max = {}
    results_max_time = {}
    results_avg_time = {}
    results_mdev = {}
    
    for folder in folders:
        filepath = os.path.join('.', folder, file_name)
        if os.path.exists(filepath):
            with open(filepath, 'r') as file:
                csv_reader = csv.reader(file)
                try:
                    header = next(csv_reader)
                except StopIteration:
                    continue
                # Corrige o cabeçalho se estiver incorreto
                if header[0] != 'num_switches' or header[1] != 'min_time' or header[2] != 'avg_time' or header[3] != 'max_time' or header[4] != 'mdev' or header[5] != 'avg_time_excl_max':
                    header = ['num_switches', 'min_time', 'avg_time', 'max_time', 'mdev', 'avg_time_excl_max']
                for row in csv_reader:
                    switchers = int(row[0])
                    if "southbound_NN" in file_name:
                        avg_time_excl_max = row[5]
                    
                        
                    max_time = row[3]
                    avg_time = row[2]
                    mdev = row[4]
                    if switchers not in results_avg_time_excl_max:
                        results_avg_time_excl_max[switchers] = {}
                        results_max_time[switchers] = {}
                        results_avg_time[switchers] = {}
                        results_mdev[switchers] = {}
                    results_avg_time_excl_max[switchers][folder] = avg_time_excl_max
                    results_max_time[switchers][folder] = max_time
                    results_avg_time[switchers][folder] = avg_time
                    results_mdev[switchers][folder] = mdev
    return results_avg_time_excl_max, results_max_time, results_avg_time, results_mdev


# Função para escrever resultados em um arquivo CSV
def write_results_to_csv(filename, results, fieldnames, folder_mapping):
    if not os.path.exists('Results'):
        os.makedirs('Results')
    filepath = os.path.join('Results', filename)
    with open(filepath, 'w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for switchers, data in results.items():
            row = {'Switchers': switchers}
            for folder, fieldname in folder_mapping.items():
                row[fieldname] = data.get(folder, '')
            writer.writerow(row)




# Nomes de campo para os arquivos CSV
fieldnames = ['Switchers', 'Traffic', 'DoS', 'Slowloris', 'RestFaults', 'MalformedPackets']
folder_mapping = {
    'traffic': 'Traffic',
    'DoS': 'DoS',
    'slowloris': 'Slowloris',
    'rest': 'RestFaults',
    'malformed': 'MalformedPackets'
}

# Iterando sobre as pastas
for file_name in file_names:
    results_avg_time_excl_max, results_max_time, results_avg_time, results_mdev = find_info(file_name)
    
    if "southbound_NN" in file_name:
        final_name = file_name[:-4]  + '_avg_time_excl_max.csv'
        write_results_to_csv(final_name, results_avg_time_excl_max, fieldnames, folder_mapping)
        print("Arquivo CSV de avg_time_excl_max gerado com sucesso:", os.path.join('Results',  final_name))
        
        final_name = file_name[:-4]  + '_max_time.csv'
        write_results_to_csv(final_name, results_max_time, fieldnames, folder_mapping)
        print("Arquivo CSV de max_time gerado com sucesso:", os.path.join('Results',  final_name))
        
        final_name = file_name[:-4]  + '_avg_time.csv'
        write_results_to_csv(final_name, results_avg_time, fieldnames, folder_mapping)
        print("Arquivo CSV de avg_time gerado com sucesso:", os.path.join('Results',  final_name))
        
        final_name = file_name[:-4]  + '_mdev.csv'
        write_results_to_csv(final_name, results_mdev, fieldnames, folder_mapping)
        print("Arquivo CSV de results_mdev gerado com sucesso:", os.path.join('Results',  final_name))

    else:
        final_name = file_name[:-4]  + '_avg_time.csv'
        write_results_to_csv(final_name, results_avg_time, fieldnames, folder_mapping)
        print("Arquivo CSV de avg_time gerado com sucesso:", os.path.join('Results',  final_name))
        
        final_name = file_name[:-4]  + '_mdev.csv'
        write_results_to_csv(final_name, results_mdev, fieldnames, folder_mapping)
        print("Arquivo CSV de results_mdev gerado com sucesso:", os.path.join('Results',  final_name))       


# Função para processar e separar resultados do D-ITG
def process_ditg_files():
    # Verifica se o argumento --details foi passado
    show_details = "--details" in sys.argv

    ditg_dirs = ['d-itg', 'ditg']
    base_dir = None
    for d in ditg_dirs:
        if os.path.exists(d):
            base_dir = d
            break
            
    if not base_dir:
        return

    print(f"Processing D-ITG files in {base_dir}...")
    
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if not file.endswith('.csv'):
                continue
                
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r') as f:
                    reader = csv.DictReader(f)
                    if not reader.fieldnames:
                        continue
                    
                    fieldnames = reader.fieldnames
                    
                    # Verifica se é um arquivo D-ITG (contém dly mean, thr mean, etc)
                    if not any('dly' in f for f in fieldnames) and not any('thr' in f for f in fieldnames):
                        continue

                    rows = list(reader)
                    
                    # Identificar chaves comuns (eixo X)
                    keys = [k for k in fieldnames if k in ['switches', 'hosts', 'num_switches', 'Switchers']]
                    
                    # Se houver colunas de switches, remover a coluna 'hosts' (redundante)
                    if any(k in keys for k in ['switches', 'num_switches', 'Switchers']) and 'hosts' in keys:
                        keys.remove('hosts')

                    # Função auxiliar para filtrar colunas detalhadas se necessário
                    def should_keep(col_name):
                        if show_details:
                            return True
                        # Palavras-chave que indicam métricas detalhadas a esconder por defeito
                        hide_keywords = ['p50', 'p90', 'p95', 'min', 'max', 'std', 'dev']
                        return not any(k in col_name.lower() for k in hide_keywords)

                    # Grupo 1: Throughput
                    thr_fields = keys + [k for k in fieldnames if ('thr' in k or 'pairs' in k) and should_keep(k)]
                    
                    # Grupo 2: Latency/Jitter/Loss
                    lat_fields = keys + [k for k in fieldnames if ('dly' in k or 'jit' in k or 'loss' in k) and should_keep(k)]
                    
                    # Output filenames
                    base_name = os.path.splitext(file)[0]
                    parent = os.path.basename(root)
                    # Adiciona o nome da pasta pai (ex: onos) se não estiver no nome do arquivo
                    if parent != base_dir and parent not in base_name:
                        base_name = f"{parent}_{base_name}"
                    
                    if not os.path.exists('Results'):
                        os.makedirs('Results')

                    # Escrever Throughput
                    if len(thr_fields) > len(keys):
                        out_path = os.path.join('Results', f"{base_name}_throughput.csv")
                        with open(out_path, 'w', newline='') as out_f:
                            writer = csv.DictWriter(out_f, fieldnames=thr_fields)
                            writer.writeheader()
                            for row in rows:
                                filtered_row = {k: row.get(k, '') for k in thr_fields}
                                writer.writerow(filtered_row)
                        print(f"Arquivo CSV de throughput gerado com sucesso: {out_path}")

                    # Escrever Latency
                    if len(lat_fields) > len(keys):
                        out_path = os.path.join('Results', f"{base_name}_latency_jitter_loss.csv")
                        with open(out_path, 'w', newline='') as out_f:
                            writer = csv.DictWriter(out_f, fieldnames=lat_fields)
                            writer.writeheader()
                            for row in rows:
                                filtered_row = {k: row.get(k, '') for k in lat_fields}
                                writer.writerow(filtered_row)
                        print(f"Arquivo CSV de latency/jitter/loss gerado com sucesso: {out_path}")

            except Exception as e:
                print(f"Erro ao processar {filepath}: {e}")

# Processar arquivos D-ITG
process_ditg_files()