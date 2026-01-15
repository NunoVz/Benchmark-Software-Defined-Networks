from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import subprocess
import os
import shlex
import shutil
import sys
import json
import paramiko
import pandas as pd
import numpy as np
import re
from datetime import datetime
from pandas.errors import EmptyDataError, ParserError
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

SUDO_PASSWORD = os.getenv("SUDO_PASSWORD")
BENCHMARK_DIR = os.getenv("BENCHMARK_DIR")
CONTROLLER_IP = os.getenv("CONTROLLER_IP")
CONTROLLER_USER = os.getenv("CONTROLLER_USER")
CONTROLLER_KEY = os.getenv("CONTROLLER_KEY")

LOG_FILES = {
    "onos": "/root/onos/apache-karaf-4.2.14/data/log/karaf.log",
    "ryu": "/var/log/ryu.log",
    "odl": "/opt/opendaylight/data/log/karaf.log",
    "floodlight": "/var/log/floodlight.log"
}
RESOURCES_DIR = os.path.abspath("Resources")
TOOL_OUTPUT_DIR = os.getenv("TOOL_OUTPUT_DIR")


ATTACK_SCENARIOS = ["malformed", "rest", "slowloris", "traffic", "dos"]

def detect_scenario(category, filename):
    cat = category.lower()
    base = filename.lower()

    if "malformed" in cat or "malformed" in base:
        return "malformed"
    if "rest" in cat or "rest" in base:
        return "rest"
    if "slowloris" in cat or "slowloris" in base:
        return "slowloris"
    if "dos" in cat or "dos" in base:
        return "dos"
    if "traffic" in cat or "traffic" in base:
        return "baseline" # Treat "traffic" as the baseline
    return "baseline"


def parse_standard_filename(category, filename):
    name = filename.replace(".csv", "").replace(".CSV", "")
    lower = name.lower()

    # controller
    if "onos" in lower:
        controller = "onos"
    elif "ryu" in lower:
        controller = "ryu"
    elif "odl" in lower or "opendaylight" in lower:
        controller = "odl"
    elif "floodlight" in lower:
        controller = "floodlight"
    else:
        controller = "unknown"

    # topology
    if "mesh" in lower:
        topo = "mesh"
    elif "3-tier" in lower or "3_tier" in lower or "3tier" in lower:
        topo = "3-tier"
    elif "star" in lower:
        topo = "star"
    elif "leaf-spine" in lower or "leafspine" in lower:
        topo = "leaf-spine"
    else:
        topo = "unknown"


    # interface type
    if "northbound" in lower:
        iface = "northbound"
    elif "southbound" in lower:
        iface = "southbound"
    elif "rppt" in lower:
        iface = "rppt"
    elif "pppt" in lower:
        iface = "pppt"
    else:
        iface = "unknown"

    # mode
    if "_nn_" in lower or "nn_api" in lower:
        mode = "nn"
    elif "_nnp" in lower:
        mode = "nnp"
    elif "_p_" in lower or "pppt" in lower:
        mode = "proactive"
    elif "_r_" in lower or "rppt" in lower:
        mode = "reactive"
    elif "northbound" in lower:
        mode = "api"
    else:
        mode = "unknown"

    # metric
    if "d-itg" in lower or "ditg" in lower:
        metric = "d-itg"
    elif "latency" in lower:
        metric = "latency"
    elif "throughput" in lower:
        metric = "throughput"
    elif "rtt" in lower:
        metric = "rtt"
    elif "discovery" in lower or "tdt" in lower:
        metric = "discovery"
    else:
        metric = "unknown"

    scenario = detect_scenario(category, filename)

    label = f"{controller.upper()} | {topo.upper()} | {iface.upper()} | {mode.upper()} | {metric.upper()} | {scenario.upper()}"
    return label


def parse_ditg_filename(controller, filename):
    base = filename.replace(".csv", "").replace(".CSV", "").lower()

    ctrl = controller.lower()

    if "mesh" in base:
        topo = "mesh"
    elif "3-tier" in base or "3_tier" in base or "3tier" in base:
        topo = "3-tier"
    elif "star" in base:
        topo = "star"
    elif "leaf-spine" in base or "leafspine" in base:
        topo = "leaf-spine"
    else:
        topo = "unknown"


    mode = "r"  

    if "malformed" in base:
        scenario = "malformed"
    elif "rest_faults" in base or "rest" in base:
        scenario = "rest"
    elif "slowloris" in base:
        scenario = "slowloris"
    elif "traffic" in base:
        scenario = "traffic"
    elif "dos" in base:
        scenario = "dos"
    else:
        scenario = "baseline"

    metric_group = "d-itg"

    label = f"{ctrl.upper()} | {topo.upper()} | {metric_group.upper()} | {mode.upper()} | {scenario.upper()}"
    return label


def parse_folder_name(folder_name):
    category = 'Unknown'
    date = None
    
    if folder_name.endswith('P'):
        category = 'Proactive'
    elif folder_name.endswith('R'):
        category = 'Reactive'
    
    # Try to find a date in MM_DD_YYYY format
    match = re.search(r'(\d{1,2})_(\d{1,2})_(\d{4})', folder_name)
    if match:
        try:
            month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            date = datetime(year, month, day)
        except (ValueError, IndexError):
            date = None
    
    # Fallback for DD_MM if no year found
    if not date:
        match = re.search(r'(\d{1,2})_(\d{1,2})', folder_name)
        if match:
            try:
                # To avoid ambiguity between MM_DD and DD_MM, we need a convention.
                # Assuming DD_MM if no year, as it's common in some places.
                day, month = int(match.group(1)), int(match.group(2))
                # Assume current year for sorting if no year is in filename
                date = datetime(datetime.now().year, month, day)
            except (ValueError, IndexError):
                date = None

    return category, date


def apply_units(df, filename):
    """
    Renomeia as colunas do DataFrame para incluir unidades (ms, s, kbps, etc.)
    com base no nome do ficheiro e nas colunas existentes.
    """
    fname = filename.lower()
    cols = df.columns.tolist()
    rename_map = {}
    
    # --- D-ITG (Jitter, Delay, Loss, Throughput) ---
    # Deteta D-ITG pelo nome do ficheiro OU pela presença de colunas específicas
    is_ditg_file = "d-itg" in fname or "ditg" in fname or "latency_jitter_loss" in fname
    has_ditg_cols = "dly_mean" in cols or "jit_mean" in cols or "loss_mean" in cols or "thr_mean" in cols

    if is_ditg_file or has_ditg_cols:
        rename_map = {
            "dly_mean": "Average Delay (ms)",
            "jit_mean": "Average Jitter (ms)",
            "loss_mean": "Average Packet Loss (%)",
            "thr_mean": "Average Throughput (kbps)",
            "dly_p50": "Delay p50 (ms)", "dly_p90": "Delay p90 (ms)",
            "jit_p50": "Jitter p50 (ms)", "jit_p90": "Jitter p90 (ms)",
            "thr_p50": "Throughput p50 (kbps)", "thr_p90": "Throughput p90 (kbps)"
        }

    # --- Latency / RTT ---
    elif "latency" in fname or "rtt" in fname:
        # Southbound (Ping/Arping) -> ms -> RTT (Round Trip Time)
        if "southbound" in fname or "_nn_" in fname or "_r_" in fname or "reactive" in fname or "_nnp" in fname:
            
            metric_base = "RTT"
            if "_nnp" in fname:
                metric_base = "Node-to-Node Proactive Latency"
            elif "_nn_" in fname:
                metric_base = "Node-to-Node Reactive Latency"
            elif "_r_" in fname:
                metric_base = "Reactive Latency"

            rename_map = {
                "min_time": f"Min {metric_base} (ms)", 
                "avg_time": f"Avg {metric_base} (ms)",
                "max_time": f"Max {metric_base} (ms)", 
                "mdev": f"{metric_base} Std Dev (ms)",
                "avg_time_excl_max": f"Avg {metric_base} Excl Max (ms)"
            }
        
        # Northbound (API) -> s -> Response Time
        elif "northbound" in fname:
            rename_map = {
                "min_value": "Min Northbound Response Time (s)", 
                "avg_value": "Avg Northbound Response Time (s)",
                "max_value": "Max Northbound Response Time (s)", 
                "mdev_value": "Northbound Response Time Std Dev (s)"
            }

        # Mimic (Cbench) -> s -> Controller Processing Time / RTT
        elif "pppt" in fname or "rppt" in fname:
            metric_base = "Controller RTT"
            if "pppt" in fname:
                metric_base = "Proactive Path Provisioning Time"
            elif "rppt" in fname:
                metric_base = "Reactive Path Provisioning Time"

            rename_map = {
                "min_value": f"Min {metric_base} (s)", 
                "avg_value": f"Avg {metric_base} (s)",
                "max_value": f"Max {metric_base} (s)", 
                "mdev_value": f"{metric_base} Std Dev (s)"
            }

    # --- Topology Discovery -> s ---
    elif "discovery" in fname or "tdt" in fname:
        rename_map = {
            "avg_tdt": "Avg Topology Discovery Time (s)", 
            "avg_ldt": "Avg Link Discovery Time (s)",
            "avg_total": "Avg Total Discovery Time (s)"
        }

    # --- Throughput (Genérico) ---
    elif "throughput" in fname:
        # Cbench -> responses/s (ou flows/s)
        if "pppt" in fname or "rppt" in fname:
            metric_base = "Throughput"
            if "pppt" in fname:
                metric_base = "Proactive Path Provisioning Throughput"
            elif "rppt" in fname:
                metric_base = "Reactive Path Provisioning Throughput"

            rename_map = {
                "throughput": f"{metric_base} (responses/s)"
            }
        # Northbound/Southbound -> req/s (pedidos API ou Pings por segundo)
        else:
            metric_base = "Throughput"
            if "_nnp" in fname:
                metric_base = "Node-to-Node Proactive Throughput"
            elif "_nn_" in fname:
                metric_base = "Node-to-Node Reactive Throughput"
            elif "_r_" in fname:
                metric_base = "Reactive Throughput"
            elif "northbound" in fname:
                metric_base = "Northbound Throughput"

            rename_map = {
                "throughput": f"{metric_base} (req/s)", 
                "max_throughput": f"Max {metric_base} (req/s)",
                "avg_throughput": f"Avg {metric_base} (req/s)",
                "min_throughput": f"Min {metric_base} (req/s)",
                "avg_tp": f"Avg {metric_base} (req/s)", 
                "min_tp": f"Min {metric_base} (req/s)",
                "max_tp": f"Max {metric_base} (req/s)"
            }

    if rename_map:
        # Extend map for merged columns (_min, _max)
        for key, new_name in list(rename_map.items()):
            # Check for _min suffix
            min_col = f"{key}_min"
            if min_col in cols:
                rename_map[min_col] = f"{new_name}_min"
            
            # Check for _max suffix
            max_col = f"{key}_max"
            if max_col in cols:
                rename_map[max_col] = f"{new_name}_max"

        df.rename(columns=rename_map, inplace=True)

    return df


def filter_metrics(df, details=False):
    """
    Filtra as colunas do DataFrame para mostrar apenas médias/throughput
    a menos que details=True.
    """
    if details:
        return df
    
    cols_to_keep = []
    all_cols = df.columns.tolist()
    
    # Colunas de Eixo X / Metadados que devem ser sempre mantidas
    x_axis_cols = ['num_switches', 'hosts', 'switches', 'Switchers', 'num_nodes', 'pairs_ok']
    
    for c in all_cols:
        if c in x_axis_cols:
            cols_to_keep.append(c)
            continue
            
        c_lower = c.lower()
        
        # Keep error bar columns explicitly (merged folders)
        if c_lower.endswith('_min') or c_lower.endswith('_max'):
            cols_to_keep.append(c)
            continue

        # Palavras-chave para esconder (Min, Max, Desvio Padrão, Percentis)
        if any(x in c_lower for x in ['min ', 'max ', 'std dev', 'mdev', 'p50', 'p90', 'p95', 'min_', 'max_', 'mdev_']):
            # Exceção: Se for "Max Throughput" e NÃO houver "Avg/Average", mantemos (comum no Northbound).
            is_max_tp = 'max' in c_lower and ('throughput' in c_lower or 'tp' in c_lower)
            has_avg = any(('avg' in x.lower() or 'average' in x.lower() or 'mean' in x.lower()) for x in all_cols if x != c)
            
            if is_max_tp and not has_avg:
                cols_to_keep.append(c)
            continue
            
        # Se não for uma métrica secundária (min/max/etc), mantemos (ex: Avg, Mean, Throughput, Loss)
        cols_to_keep.append(c)
            
    return df[cols_to_keep]


def get_merge_count(folder_path):
    """Helper to read the merge count from merge_info.json if it exists."""
    try:
        with open(os.path.join(folder_path, "merge_info.json"), 'r') as f:
            return json.load(f).get('count', 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0


@app.route('/')
def list_folders_view():
    all_folders = list_folders()

    categorized_folders = {
        'Proactive': [],
        'Reactive': [],
        'Other': []
    }

    for folder in all_folders:
        cat = folder.get('category', 'Unknown')
        if cat == 'Proactive':
            categorized_folders['Proactive'].append(folder)
        elif cat == 'Reactive':
            categorized_folders['Reactive'].append(folder)
        else:
            categorized_folders['Other'].append(folder)
            
    # The 'Other' category might contain 'Output_Realtime' which we want first.
    categorized_folders['Other'].sort(key=lambda x: x['name'] != 'Output_Realtime')


    print("Categorized Folders:", categorized_folders)
    return render_template('folders.html', categorized_folders=categorized_folders)


def log_message(message):
    print(message)
    socketio.emit("log_update", {"log": message})
    sys.stdout.flush()




def list_folders():
    # Folders already present in Resources/
    raw_folders = [
        folder for folder in os.listdir(RESOURCES_DIR)
        if os.path.isdir(os.path.join(RESOURCES_DIR, folder))
    ]

    folders_info = []
    for folder_name in raw_folders:
        category, date = parse_folder_name(folder_name)
        target_path = os.path.join(RESOURCES_DIR, folder_name)
        processed = os.path.exists(os.path.join(target_path, "Results"))
        is_merged = os.path.exists(os.path.join(target_path, ".merged"))
        merge_count = get_merge_count(target_path) if is_merged else 0
        
        folders_info.append({
            "name": folder_name,
            "processed": processed,
            "is_merged": is_merged,
            "merge_count": merge_count,
            "category": category,
            "date": date.strftime('%Y-%m-%d') if date else None
        })
    
    # Sort folders by date (chronologically), putting those without a date last
    folders_info.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d') if x['date'] else datetime.max)

    # Add a virtual folder for realtime output if the directory exists
    if TOOL_OUTPUT_DIR and os.path.isdir(TOOL_OUTPUT_DIR):
        target_path = TOOL_OUTPUT_DIR
        processed = os.path.exists(os.path.join(target_path, "Results"))
        is_merged = os.path.exists(os.path.join(target_path, ".merged"))
        merge_count = get_merge_count(target_path) if is_merged else 0

        folders_info.insert(0, {
            "name": "Output_Realtime",
            "processed": processed,
            "is_merged": is_merged,
            "merge_count": merge_count,
            "category": "Realtime",
            "date": datetime.now().strftime('%Y-%m-%d')
        })

    return folders_info



def parse_filename(filename):
    name = filename.replace(".csv", "").replace(".CSV", "")
    parts = name.split("_")

    controller = next((p for p in parts if p.lower() in ["onos", "odl", "ryu", "floodlight"]), "unknown")
    topology = next((p for p in parts if p.lower() in ["mesh", "star", "3-tier", "leaf", "leaf-spine"]), "unknown")
    mode = next((p for p in parts if p.lower() in ["southbound", "northbound", "rppt"]), "unknown")
    direction = next((p for p in parts if p.lower() in ["nn", "p", "r"]), "unknown")
    metric = next((p for p in parts if p.lower() in ["latency", "throughput", "rtt"]), "unknown")

    # Build clean readable category name
    return f"{controller.upper()} | {topology.upper()} | {mode.upper()} | {direction.upper()} | {metric.upper()}"


def read_results(output_folder, details=False):
    results = {}
    folder_path = os.path.join(RESOURCES_DIR, output_folder)

    if not os.path.exists(folder_path):
        print(f"Error: {folder_path} does not exist!")
        return {}

    for category in os.listdir(folder_path):
        category_path = os.path.join(folder_path, category)
        if not os.path.isdir(category_path):
            continue

        # 1) Caso especial: D-ITG tem subpastas odl/onos/ryu
        if category.lower() in ["d-itg", "ditg"]:
            for ctrl in os.listdir(category_path):
                ctrl_path = os.path.join(category_path, ctrl)
                if not os.path.isdir(ctrl_path):
                    continue

                for filename in os.listdir(ctrl_path):
                    if not filename.endswith(".csv"):
                        continue

                    filepath = os.path.join(ctrl_path, filename)
                    print(f"[D-ITG] Reading file: {filepath}")
                    try:
                        df = pd.read_csv(filepath).replace({np.nan: None})
                        df = apply_units(df, filename)
                        df = filter_metrics(df, details)
                    except (EmptyDataError, ParserError):
                        continue

                    key = parse_ditg_filename(ctrl, filename)
                    results[key] = df.to_dict(orient="records")

            continue  # já tratámos este category

        # 2) Todos os outros folders (malformed, rest, slowloris, traffic, baseline, etc.)
        for filename in os.listdir(category_path):
            if not filename.endswith(".csv"):
                continue

            filepath = os.path.join(category_path, filename)
            print(f"[STD] Reading file: {filepath}")
            try:
                df = pd.read_csv(filepath).replace({np.nan: None})
                df = apply_units(df, filename)
                df = filter_metrics(df, details)
            except (EmptyDataError, ParserError):
                continue

            key = parse_standard_filename(category, filename)
            results[key] = df.to_dict(orient="records")

    return results


def read_realtime_results(details=False):
    results = {}

    folder_path = TOOL_OUTPUT_DIR

    if not folder_path or not os.path.isdir(folder_path):
        print(f"[REALTIME] {folder_path} does not exist!")
        return results

    print(f"[REALTIME] Loading realtime results from: {folder_path}")

    # ---------------------------------------------------------
    # 1) Same logic as read_results, but base dir = TOOL_OUTPUT_DIR
    # ---------------------------------------------------------
    for category in os.listdir(folder_path):
        category_path = os.path.join(folder_path, category)
        if not os.path.isdir(category_path):
            continue

        # Caso especial: D-ITG com subpastas odl/onos/ryu
        if category.lower() in ["d-itg", "ditg"]:
            for ctrl in os.listdir(category_path):
                ctrl_path = os.path.join(category_path, ctrl)
                if not os.path.isdir(ctrl_path):
                    continue

                for filename in os.listdir(ctrl_path):
                    if not filename.endswith(".csv"):
                        continue

                    filepath = os.path.join(ctrl_path, filename)
                    print(f"[REALTIME D-ITG] Reading file: {filepath}")
                    try:
                        df = pd.read_csv(filepath).replace({np.nan: None})
                        df = apply_units(df, filename)
                        df = filter_metrics(df, details)
                    except (EmptyDataError, ParserError) as e:
                        print(f"[REALTIME D-ITG] SKIP {filepath}: {e}")
                        continue


                    key = parse_ditg_filename(ctrl, filename)
                    # optional: mark as realtime
                    key = f"REALTIME | {key}"
                    results[key] = df.to_dict(orient="records")

            continue  # já tratámos este category

        # Outros folders (malformed, rest, slowloris, traffic, baseline, etc.)
        for filename in os.listdir(category_path):
            if not filename.endswith(".csv"):
                continue

            filepath = os.path.join(category_path, filename)
            print(f"[REALTIME STD] Reading file: {filepath}")
            try:
                df = pd.read_csv(filepath).replace({np.nan: None})
                df = apply_units(df, filename)
                df = filter_metrics(df, details)
            except (EmptyDataError, ParserError) as e:
                print(f"[REALTIME STD] SKIP {filepath}: {e}")
                continue


            key = parse_standard_filename(category, filename)
            # optional: mark as realtime
            key = f"REALTIME | {key}"
            results[key] = df.to_dict(orient="records")

   

    print(f"[REALTIME] Total groups loaded: {len(results)}")
    return results



@app.route('/run-analysis', methods=['POST'])
def run_analysis():
    data = request.get_json()
    folder = data.get('folder')
    include_details = data.get('include_details', False)

    if not folder:
        return jsonify({"error": "No folder provided"}), 400

    target_dir = TOOL_OUTPUT_DIR if folder == "Output_Realtime" else os.path.join(RESOURCES_DIR, folder)
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "make_results.py")

    try:
        # Run the script in the target directory
        cmd = [sys.executable, script_path]
        if include_details:
            cmd.append("--details")
        subprocess.run(cmd, cwd=target_dir, check=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/merge')
def merge_page():
    folders = list_folders()
    # Filter out Output_Realtime if you don't want to merge it, or keep it.
    # Usually we merge saved runs in Resources.
    return render_template('merge.html', folders=folders)


@app.route('/compare')
def compare_page():
    folders = list_folders()
    return render_template('compare.html', folders=folders)

@app.route('/thesis_view')
def thesis_view_page():
    folders = list_folders()
    return render_template('thesis_view.html', folders=folders)


@app.route('/api/merge', methods=['POST'])
def api_merge():
    data = request.get_json()
    new_name = data.get('new_name')
    selected_folders = data.get('folders')

    if not new_name or not selected_folders or len(selected_folders) < 2:
        return jsonify({"error": "Invalid input"}), 400

    new_folder_path = os.path.join(RESOURCES_DIR, new_name)
    if os.path.exists(new_folder_path):
        return jsonify({"error": "Folder already exists"}), 400

    try:
        os.makedirs(new_folder_path)
        
        # Create a marker file to identify this as a merged folder
        with open(os.path.join(new_folder_path, ".merged"), "w") as f:
            f.write("merged")
            
        # Save metadata about the merge (Sample Size N)
        with open(os.path.join(new_folder_path, "merge_info.json"), "w") as f:
            json.dump({
                "source_folders": selected_folders,
                "count": len(selected_folders),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, f, indent=2)
        
        # Use the first folder as the template for structure
        base_folder = os.path.join(RESOURCES_DIR, selected_folders[0])
        
        for root, dirs, files in os.walk(base_folder):
            # Calculate relative path to replicate structure
            rel_path = os.path.relpath(root, base_folder)
            target_dir = os.path.join(new_folder_path, rel_path)
            
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)

            for file in files:
                if file.lower().endswith('.csv'):
                    # Collect dataframes from all selected folders
                    dfs = []
                    for folder in selected_folders:
                        src_file = os.path.join(RESOURCES_DIR, folder, rel_path, file)
                        if os.path.exists(src_file):
                            try:
                                df = pd.read_csv(src_file)
                                dfs.append(df)
                            except Exception:
                                pass # Ignore unreadable files
                    
                    if dfs:
                        # Calculate mean, min, max of numeric columns
                        concat_df = pd.concat(dfs)
                        
                        # Tenta encontrar a coluna de agrupamento (Eixo X) para alinhar os dados corretamente
                        group_col = None
                        possible_x_cols = ['Switchers', 'switches', 'num_switches', 'num_nodes', 'hosts']
                        for col in possible_x_cols:
                            if col in concat_df.columns:
                                group_col = col
                                break
                        
                        if group_col:
                            # Agrupa pela coluna do eixo X (ex: num_switches) para evitar desalinhamentos
                            grouped = concat_df.groupby(group_col)
                        else:
                            # Fallback: agrupa pelo índice (comportamento antigo)
                            grouped = concat_df.groupby(level=0)
                        
                        mean_df = grouped.mean(numeric_only=True)
                        std_df = grouped.std(numeric_only=True)
                        
                        # Se agrupámos por coluna, ela agora é o índice. Reset para voltar a ser coluna.
                        if group_col:
                            mean_df.reset_index(inplace=True)
                            std_df.reset_index(inplace=True)

                        # Usamos o mean_df como base para garantir que temos todas as linhas alinhadas
                        final_df = mean_df.copy()

                        # Add min and max columns
                        for col in mean_df.columns:
                            if col == group_col: continue # Não calcular min/max para o eixo X
                            if col in std_df.columns:
                                final_df[f"{col}_min"] = (mean_df[col] - std_df[col]).clip(lower=0)
                                final_df[f"{col}_max"] = mean_df[col] + std_df[col]
                        
                        # Force integer columns to be integers to avoid "12.2 switches"
                        integer_columns = ['Switchers', 'switches', 'num_switches', 'hosts', 'num_nodes', 'pairs_ok']
                        for col in integer_columns:
                            if col in final_df.columns:
                                final_df[col] = pd.to_numeric(final_df[col], errors='coerce').fillna(0).round().astype(int)

                        # Reorder columns to ensure Switchers is first (X-axis)
                        cols = final_df.columns.tolist()
                        x_axis_candidates = ['Switchers', 'switches', 'num_switches', 'hosts']
                        for candidate in x_axis_candidates:
                            if candidate in cols:
                                cols.insert(0, cols.pop(cols.index(candidate)))
                                break
                        final_df = final_df[cols]
                        
                        final_df.to_csv(os.path.join(target_dir, file), index=False)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/similarity', methods=['POST'])
def api_similarity():
    data = request.get_json()
    selected_folders = data.get('folders')

    if not selected_folders or len(selected_folders) < 2:
        return jsonify({"error": "Select at least 2 folders to compare"}), 400

    folder_data = {}
    all_metrics = []

    try:
        # 1. Load data for all folders
        for folder in selected_folders:
            folder_path = os.path.join(RESOURCES_DIR, folder)
            folder_data[folder] = []
            
            for root, _, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith('.csv'):
                        try:
                            df = pd.read_csv(os.path.join(root, file))
                        except (EmptyDataError, ParserError):
                            continue
                            
                        # Identify X-axis
                        x_col = next((c for c in ['Switchers', 'switches', 'num_switches'] if c in df.columns), None)
                        if not x_col: continue
                        
                        # Get numeric columns only
                        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                        for col in numeric_cols:
                            if col == x_col: continue
                            for _, row in df.iterrows():
                                all_metrics.append({
                                    'folder': folder,
                                    'file': file,
                                    'metric': col,
                                    'x': row[x_col],
                                    'val': row[col]
                                })

        if not all_metrics:
            return jsonify({"error": "No numeric data found to compare"}), 400

        df_all = pd.DataFrame(all_metrics)
        
        # 2. Calculate global mean per (file, metric, x)
        means = df_all.groupby(['file', 'metric', 'x'])['val'].transform('mean')
        
        # 3. Calculate absolute percentage deviation from the mean
        # We use a small epsilon to avoid division by zero
        df_all['deviation'] = (np.abs(df_all['val'] - means) / (means + 1e-9)) * 100
        
        # 4. Aggregate deviation per folder
        folder_scores = df_all.groupby('folder')['deviation'].mean().to_dict()
        
        # Format results for the UI
        results = []
        for folder in selected_folders:
            score = folder_scores.get(folder, 0)
            status = "Consistent"
            if score > 20: status = "Outlier"
            elif score > 10: status = "Variable"
            
            results.append({
                "name": folder,
                "deviation": round(score, 2),
                "status": status
            })
            
        # Sort by deviation (best first)
        results.sort(key=lambda x: x['deviation'])

        return jsonify({
            "success": True,
            "results": results
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/delete-folder', methods=['POST'])
def delete_folder():
    data = request.get_json()
    folder = data.get('folder')
    password = data.get('password')

    if not folder:
        return jsonify({"error": "No folder provided"}), 400

    # Verifica a password (usa a mesma definida para sudo ou altera aqui)
    if password != SUDO_PASSWORD:
        return jsonify({"error": "Invalid password"}), 403

    # Determina o caminho alvo
    if folder == "Output_Realtime":
        target_path = TOOL_OUTPUT_DIR
    else:
        target_path = os.path.join(RESOURCES_DIR, folder)

    if not os.path.exists(target_path):
        return jsonify({"error": "Folder not found"}), 404

    try:
        shutil.rmtree(target_path)
        # Se for a pasta realtime, recria-a vazia para não quebrar a tool
        if folder == "Output_Realtime":
            os.makedirs(target_path, exist_ok=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def parse_standard_filename_as_dict(category, filename):
    name = filename.replace(".csv", "").replace(".CSV", "")
    lower = name.lower()

    # controller
    if "onos" in lower:
        controller = "onos"
    elif "ryu" in lower:
        controller = "ryu"
    elif "odl" in lower or "opendaylight" in lower:
        controller = "odl"
    elif "floodlight" in lower:
        controller = "floodlight"
    else:
        controller = "unknown"

    # topology
    if "mesh" in lower:
        topo = "mesh"
    elif "3-tier" in lower or "3_tier" in lower or "3tier" in lower:
        topo = "3-tier"
    elif "star" in lower:
        topo = "star"
    elif "leaf-spine" in lower or "leafspine" in lower:
        topo = "leaf-spine"
    else:
        topo = "unknown"


    # interface type
    if "northbound" in lower:
        iface = "northbound"
    elif "southbound" in lower:
        iface = "southbound"
    elif "rppt" in lower:
        iface = "rppt"
    elif "pppt" in lower:
        iface = "pppt"
    else:
        iface = "unknown"

    # mode
    if "_nnp" in lower:
        mode = "nnp"
    elif "_nn_" in lower or "nn_api" in lower:
        mode = "nn"
    elif "_p_" in lower or "pppt" in lower:
        mode = "proactive"
    elif "_r_" in lower or "rppt" in lower:
        mode = "reactive"
    elif "northbound" in lower:
        mode = "api"
    else:
        mode = "unknown"

    # metric
    if "d-itg" in lower or "ditg" in lower:
        metric = "d-itg"
    elif "latency" in lower:
        metric = "latency"
    elif "throughput" in lower:
        metric = "throughput"
    elif "rtt" in lower:
        metric = "rtt"
    elif "discovery" in lower or "tdt" in lower:
        metric = "discovery"
    else:
        metric = "unknown"

    scenario = detect_scenario(category, filename)

    label = f"{controller.upper()} | {topo.upper()} | {iface.upper()} | {mode.upper()} | {metric.upper()} | {scenario.upper()}"
    
    # Combine metric and interface for better distinction in comparison view
    display_metric = metric.upper()
    if mode in ["nn", "nnp"]:
        display_metric = f"{metric.upper()} ({iface.upper()} {mode.upper()})"
    elif iface != "unknown":
        display_metric = f"{metric.upper()} ({iface.upper()})"

    return {
        "controller": controller.upper(),
        "topology": topo.upper(),
        "iface": iface.upper(),
        "mode": mode.upper(),
        "metric": display_metric,
        "scenario": scenario.upper(),
        "label": label
    }


def parse_ditg_filename_as_dict(controller, filename):
    base = filename.replace(".csv", "").replace(".CSV", "").lower()
    ctrl = controller.lower()

    if "mesh" in base:
        topo = "mesh"
    elif "3-tier" in base or "3_tier" in base or "3tier" in base:
        topo = "3-tier"
    elif "star" in base:
        topo = "star"
    elif "leaf-spine" in base or "leafspine" in base:
        topo = "leaf-spine"
    else:
        topo = "unknown"

    mode = "r"  

    if "malformed" in base:
        scenario = "malformed"
    elif "rest_faults" in base or "rest" in base:
        scenario = "rest"
    elif "slowloris" in base:
        scenario = "slowloris"
    elif "traffic" in base:
        scenario = "traffic"
    elif "dos" in base:
        scenario = "dos"
    else:
        scenario = "baseline"

    metric_group = "d-itg"
    label = f"{ctrl.upper()} | {topo.upper()} | {metric_group.upper()} | {mode.upper()} | {scenario.upper()}"
    return {
        "controller": ctrl.upper(),
        "topology": topo.upper(),
        "iface": metric_group.upper(),
        "mode": mode.upper(),
        "metric": "D-ITG",
        "scenario": scenario.upper(),
        "label": label
    }


def get_comparison_data(output_folder, details=False):
    results = []
    
    folder_path = None
    if output_folder == "Output_Realtime":
        if TOOL_OUTPUT_DIR and os.path.isdir(TOOL_OUTPUT_DIR):
            folder_path = TOOL_OUTPUT_DIR
    else:
        path_candidate = os.path.join(RESOURCES_DIR, output_folder)
        if os.path.isdir(path_candidate):
            folder_path = path_candidate
    
    if not folder_path:
        print(f"Error: Could not find a valid path for {output_folder}!")
        return []

    # Use os.walk to find all CSV files recursively, supporting nested structures from batch exports
    for root, dirs, files in os.walk(folder_path):
        category = os.path.basename(root)
        
        for filename in files:
            if not filename.endswith(".csv"):
                continue
                
            filepath = os.path.join(root, filename)
            is_ditg = "d-itg" in root.lower() or "ditg" in root.lower() or "d-itg" in filename.lower()
            
            try:
                df = pd.read_csv(filepath)
                # Coerce numeric columns to handle "None"/"NA" strings often found in failed runs
                for col in df.columns:
                    if any(x in col.lower() for x in ['time', 'throughput', 'tp', 'rtt', 'latency', 'delay', 'jitter', 'loss', 'value']):
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                
                df = df.replace({np.nan: None})
                df = apply_units(df, filename)
                df = filter_metrics(df, details)
                if df.empty: continue
                
                if is_ditg:
                    # Extract controller from path or filename
                    ctrl = "unknown"
                    for c in ["onos", "odl", "ryu", "floodlight"]:
                        if c in root.lower() or c in filename.lower():
                            ctrl = c
                            break
                    parsed_info = parse_ditg_filename_as_dict(ctrl, filename)
                else:
                    parsed_info = parse_standard_filename_as_dict(category, filename)
                
                # Skip auxiliary files (like faults.csv or logs) that don't match our benchmark naming convention
                if parsed_info["controller"] == "UNKNOWN" or parsed_info["topology"] == "UNKNOWN":
                    continue

                parsed_info["data"] = df.to_dict(orient="records")
                results.append(parsed_info)
            except Exception as e:
                print(f"Skipping {filepath}: {e}")
                continue
    return results


@app.route('/api/comparison_data/<output_folder>')
def api_comparison_data(output_folder):
    details = request.args.get('details') == 'true'
    data = get_comparison_data(output_folder, details=details)
    
    # Check for merge info to return metadata (Sample Size)
    folder_path = None
    if output_folder == "Output_Realtime":
        if TOOL_OUTPUT_DIR and os.path.isdir(TOOL_OUTPUT_DIR):
            folder_path = TOOL_OUTPUT_DIR
    else:
        path_candidate = os.path.join(RESOURCES_DIR, output_folder)
        if os.path.isdir(path_candidate):
            folder_path = path_candidate
            
    merge_count = 0
    is_merged = False
    if folder_path:
        is_merged = os.path.exists(os.path.join(folder_path, ".merged"))
        merge_count = get_merge_count(folder_path) if is_merged else 0

    return jsonify({
        "data": data,
        "meta": {
            "is_merged": is_merged,
            "merge_count": merge_count
        }
    })


@app.route('/results/<output_folder>')
def results_page(output_folder):
    folder_path = os.path.join(RESOURCES_DIR, output_folder)
    is_merged = os.path.exists(os.path.join(folder_path, ".merged"))
    merge_count = get_merge_count(folder_path) if is_merged else 0
    return render_template('results.html', output_folder=output_folder, merge_count=merge_count)

@app.route('/api/results/<output_folder>')
def api_results(output_folder):
    details = request.args.get('details') == 'true'
    if output_folder == "Output_Realtime":
        results = read_realtime_results(details=details)
    else:
        results = read_results(output_folder, details=details)

    return jsonify(results)



if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=8080, debug=True)