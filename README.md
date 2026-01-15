# SDN Security & Testing Framework

Este projeto é uma framework avançada para testes automatizados de segurança, robustez e desempenho de controladores SDN (Software Defined Networking). A ferramenta orquestra ambientes de teste complexos, executa uma variedade de cargas de trabalho (benchmarks, ataques DoS, injeção de falhas) e fornece uma interface gráfica para análise de resultados.

A sua principal vantagem é a **automação completa do ciclo de vida do ambiente de teste**, garantindo que cada execução é isolada, limpa e reprodutível.

## 🏛️ Arquitetura e Fluxo de Trabalho

O sistema opera de forma distribuída e automatizada, utilizando o Xen Orchestra para gestão da infraestrutura e gRPC para comunicação. O fluxo de trabalho de um teste típico é o seguinte:

1.  **Início via GUI:** O utilizador utiliza a interface gráfica (`gui/backend/app.py`) para configurar e iniciar um novo teste.
2.  **Orquestração Central (`benchmark.py`):** O pedido da GUI aciona o orquestrador principal. Este módulo é o cérebro da framework e coordena todos os passos seguintes.
3.  **Provisionamento da VM Mininet:** O orquestrador invoca o módulo `xenorchestra.py`, que comunica com a API do **Xen Orchestra** para clonar uma VM Mininet a partir de um template pré-definido. Isto garante que cada teste corre numa VM "limpa", eliminando interferências de execuções anteriores. A VM é destruída no final do teste.
4.  **Ativação do Controlador SDN:** Em paralelo, o orquestrador conecta-se via SSH à VM do Controlador e utiliza comandos **Docker** para iniciar a instância do controlador SDN especificada (ONOS, ODL, Ryu).
5.  **Comunicação via gRPC:** Assim que as VMs estão prontas, o orquestrador comunica com o servidor `mininet_server.py` (a correr na VM Mininet) através de uma **API gRPC** (`mininet_control.proto`). Este envia comandos para construir a topologia de rede, gerar tráfego, e manipular links.
6.  **Execução dos Testes:** O orquestrador executa o plano de teste, que pode incluir:
    *   Benchmarks de desempenho do plano de controlo (`mimic_cbench.py`).
    *   Ataques de negação de serviço (DoS) como Xerxes e Slowloris (`attackload.py`).
    *   Injeção de falhas na API REST e pacotes malformados (`faultload.py`).
7.  **Recolha e Análise de Resultados:** Os resultados são guardados em ficheiros `.csv` no diretório `Tool/output`. A GUI permite ao utilizador visualizar, processar e até fundir resultados de múltiplos testes para análise comparativa.

## 🚀 Funcionalidades

### 1. Orquestração e Automação
*   **Ambientes de Teste Descartáveis:** Integração com **Xen Orchestra** para provisionar e destruir automaticamente a VM de emulação de rede (Mininet) para cada teste, garantindo isolamento total.
*   **Gestão de Controladores via Docker:** Automatiza o ciclo de vida dos controladores SDN (ONOS, ODL, Ryu) em contentores Docker.
*   **Comunicação Estruturada:** Utiliza uma API gRPC para controlo robusto e fiável do ambiente Mininet, em vez de comandos SSH frágeis.

### 2. Testes de Segurança e Robustez
*   **Ataques de Negação de Serviço (DoS):** Lança ataques como **Xerxes** (DoS a nível de aplicação) e **Slowloris** (DoS a nível de rede) para testar a resiliência do controlador (`attackload.py`).
*   **Injeção de Falhas (Fault Injection):**
    *   **REST API Fuzzing:** Analisa especificações OpenAPI (YAML) e injeta dados inválidos nos endpoints da API Northbound para detetar vulnerabilidades.
    *   **Pacotes Malformados:** Envia pacotes corrompidos para testar o tratamento de erros do plano de dados.

### 3. Benchmarking e Análise de Desempenho
*   **Benchmark de Desempenho do Controlador:** Utiliza `mimic_cbench.py` para medir a latência e o throughput do plano de controlo.
*   **Testes de API Northbound:** Mede o desempenho da API REST do controlador (`northbound_api.py`).
*   **Provisionamento Proativo:** Automatiza a instalação de regras de fluxo (Flow Rules) para ARP, ICMP e encaminhamento L2, garantindo um estado de rede base para os testes.

## 🖥️ Interface Gráfica (GUI) - Guia de Utilização

A interface web, construída com Flask (`gui/backend/app.py`), é o ponto central para a visualização e análise de todos os resultados gerados pela framework. Ela foi desenhada para ser um dashboard analítico poderoso, permitindo não só a visualização de testes individuais, mas também a agregação estatística de múltiplos resultados.

Abaixo encontra-se um guia detalhado das suas páginas e API interna.

### Páginas Principais

Estas são as páginas com as quais um utilizador interage diretamente.

| Rota (URL) | Template | Nome da Página | Funcionalidade Principal |
| :--- | :--- | :--- | :--- |
| `/` | `folders.html` | **Dashboard de Resultados** | Página inicial. Lista todas as pastas de resultados disponíveis, incluindo a pasta virtual `Output_Realtime` para monitorização em tempo real. Indica se uma pasta já foi processada ou se é fruto de uma agregação (`merge`). |
| `/results/<pasta>` | `results.html` | **Visualizador de Testes** | A página de análise principal. Carrega e exibe os dados da pasta de resultados selecionada, renderizando múltiplos gráficos e tabelas para cada métrica e cenário de teste. |
| `/merge` | `merge.html` | **Agregação de Resultados** | Apresenta uma interface para selecionar múltiplas pastas de resultados. O utilizador pode escolher as pastas que deseja combinar e dar um novo nome ao conjunto de dados agregado que será gerado. |

### Lógica de Funcionamento e API Interna

A interface utiliza um conjunto de endpoints de API para carregar dados de forma dinâmica e executar operações no backend.

| Rota (URL) | Método | Descrição da API |
| :--- | :--- | :--- |
| `/api/results/<pasta>` | `GET` | **Fornecedor de Dados para Gráficos:** Endpoint chamado pela página de resultados. Lê todos os ficheiros `.csv` da pasta especificada, analisa de forma inteligente os nomes dos ficheiros para gerar etiquetas descritivas (ex: `ONOS | MESH | API | THROUGHPUT`), e retorna todos os dados em formato JSON. |
| `/api/merge` | `POST` | **Motor de Agregação Estatística:** Recebe uma lista de pastas e um novo nome. Cria uma nova pasta de resultados onde cada `.csv` é a **média estatística** (mean, min, max) dos ficheiros correspondentes nas pastas de origem. Essencial para analisar a variabilidade entre múltiplos testes. |
| `/run-analysis` | `POST` | **Pós-processamento:** Executa o script `make_results.py` numa pasta de resultados para gerar análises ou agregações adicionais. |
| `/delete-folder` | `POST` | **Gestão de Pastas:** Permite apagar uma pasta de resultados do servidor (requer uma password de segurança para evitar eliminações acidentais). |

O sistema de parsing de nomes de ficheiro (`parse_standard_filename` e `parse_ditg_filename` em `app.py`) é uma peça chave, pois permite à GUI categorizar e legendar automaticamente os dados de acordo com:
*   Controlador (ONOS, Ryu, ODL)
*   Topologia (Mesh, 3-tier)
*   Modo (Proactive, Reactive, NN)
*   Métrica (Latency, Throughput, RTT)
*   Cenário de Teste (Baseline, Malformed, REST, DoS)

## 📂 Estrutura do Projeto

*   `Tool/benchmark.py`: **O orquestrador principal.** Coordena todo o fluxo de trabalho.
*   `Tool/xenorchestra.py`: Módulo de integração com o Xen Orchestra para gestão automática das VMs Mininet.
*   `Mininet/mininet_server.py`: Servidor gRPC que corre na VM Mininet e executa os comandos recebidos.
*   `Tool/mininet_control.proto`: A definição formal da API gRPC entre o orquestrador e o servidor Mininet.
*   `gui/backend/app.py`: A aplicação Flask que serve a interface gráfica de análise de resultados.
*   `Tool/faultload.py`: Motor de injeção de falhas (REST Fuzzing e Pacotes Malformados).
*   `Tool/attackload.py`: Módulo para lançamento de ataques de negação de serviço (DoS).
*   `Tool/mimic_cbench.py`: Ferramenta para benchmarking do desempenho do controlador.
*   `Tool/run.py`: Script auxiliar com funções para gerir os controladores SDN via SSH e Docker.

## 🛠️ Pré-requisitos

*   Python 3.x
*   Acesso de API ao Xen Orchestra.
*   VMs pré-configuradas (para o Controlador e como template para a Mininet).
*   Docker instalado na VM do Controlador.

## 📄 Licença

Este projeto utiliza componentes sob as licenças CeCILL V2 e GNU GPLv3. Consulte a pasta `sourcesonoff` para mais detalhes.

---

# SDN Security & Testing Framework (English Version)

This project is an advanced framework for automated security, robustness, and performance testing of SDN (Software Defined Networking) controllers. The tool orchestrates complex test environments, executes a variety of workloads (benchmarks, DoS attacks, fault injection), and provides a graphical interface for result analysis.

Its main advantage is the **complete automation of the test environment lifecycle**, ensuring that each execution is isolated, clean, and reproducible.

## 🏛️ Architecture and Workflow

The system operates in a distributed and automated manner, using Xen Orchestra for infrastructure management and gRPC for communication. The workflow of a typical test is as follows:

1.  **Start via GUI:** The user uses the graphical interface (`gui/backend/app.py`) to configure and start a new test.
2.  **Central Orchestration (`benchmark.py`):** The GUI request triggers the main orchestrator. This module is the brain of the framework and coordinates all subsequent steps.
3.  **Mininet VM Provisioning:** The orchestrator invokes the `xenorchestra.py` module, which communicates with the **Xen Orchestra** API to clone a Mininet VM from a pre-defined template. This ensures each test runs in a "clean" VM, eliminating interference from previous runs. The VM is destroyed at the end of the test.
4.  **SDN Controller Activation:** In parallel, the orchestrator connects via SSH to the Controller VM and uses **Docker** commands to start the specified SDN controller instance (ONOS, ODL, Ryu).
5.  **Communication via gRPC:** Once the VMs are ready, the orchestrator communicates with the `mininet_server.py` server (running on the Mininet VM) via a **gRPC API** (`mininet_control.proto`). This sends commands to build the network topology, generate traffic, and manipulate links.
6.  **Test Execution:** The orchestrator executes the test plan, which may include:
    *   Control plane performance benchmarks (`mimic_cbench.py`).
    *   Denial of Service (DoS) attacks like Xerxes and Slowloris (`attackload.py`).
    *   Fault injection into the REST API and malformed packets (`faultload.py`).
7.  **Result Collection and Analysis:** Results are saved in `.csv` files in the `Tool/output` directory. The GUI allows the user to visualize, process, and even merge results from multiple tests for comparative analysis.

## 🚀 Features

### 1. Orchestration and Automation
*   **Disposable Test Environments:** Integration with **Xen Orchestra** to automatically provision and destroy the network emulation VM (Mininet) for each test, ensuring total isolation.
*   **Controller Management via Docker:** Automates the lifecycle of SDN controllers (ONOS, ODL, Ryu) in Docker containers.
*   **Structured Communication:** Uses a gRPC API for robust and reliable control of the Mininet environment, instead of fragile SSH commands.

### 2. Security and Robustness Tests
*   **Denial of Service (DoS) Attacks:** Launches attacks like **Xerxes** (Application layer DoS) and **Slowloris** (Network layer DoS) to test controller resilience (`attackload.py`).
*   **Fault Injection:**
    *   **REST API Fuzzing:** Analyzes OpenAPI specifications (YAML) and injects invalid data into Northbound API endpoints to detect vulnerabilities.
    *   **Malformed Packets:** Sends corrupted packets to test data plane error handling.

### 3. Benchmarking and Performance Analysis
*   **Controller Performance Benchmark:** Uses `mimic_cbench.py` to measure control plane latency and throughput.
*   **Northbound API Tests:** Measures controller REST API performance (`northbound_api.py`).
*   **Proactive Provisioning:** Automates the installation of flow rules (ARP, ICMP, and L2 forwarding), ensuring a baseline network state for tests.

## 🖥️ Graphical Interface (GUI) - User Guide

The web interface, built with Flask (`gui/backend/app.py`), is the central point for visualizing and analyzing all results generated by the framework. It was designed as a powerful analytical dashboard, allowing not only the visualization of individual tests but also the statistical aggregation of multiple results.

Below is a detailed guide to its pages and internal API.

### Main Pages

These are the pages a user interacts with directly.

| Route (URL) | Template | Page Name | Main Functionality |
| :--- | :--- | :--- | :--- |
| `/` | `folders.html` | **Results Dashboard** | Home page. Lists all available result folders, including the virtual folder `Output_Realtime` for real-time monitoring. Indicates if a folder has already been processed or if it is the result of an aggregation (`merge`). |
| `/results/<folder>` | `results.html` | **Test Viewer** | The main analysis page. Loads and displays data from the selected result folder, rendering multiple charts and tables for each metric and test scenario. |
| `/merge` | `merge.html` | **Result Aggregation** | Presents an interface to select multiple result folders. The user can choose folders to combine and name the new aggregated dataset that will be generated. |

### Operational Logic and Internal API

The interface uses a set of API endpoints to load data dynamically and execute backend operations.

| Route (URL) | Method | API Description |
| :--- | :--- | :--- |
| `/api/results/<folder>` | `GET` | **Data Provider for Charts:** Endpoint called by the results page. Reads all `.csv` files in the specified folder, intelligently parses filenames to generate descriptive labels (e.g., `ONOS | MESH | API | THROUGHPUT`), and returns all data in JSON format. |
| `/api/merge` | `POST` | **Statistical Aggregation Engine:** Receives a list of folders and a new name. Creates a new result folder where each `.csv` is the **statistical average** (mean, min, max) of the corresponding files in the source folders. Essential for analyzing variability across multiple tests. |
| `/run-analysis` | `POST` | **Post-processing:** Executes the `make_results.py` script on a result folder to generate additional analyses or aggregations. |
| `/delete-folder` | `POST` | **Folder Management:** Allows deleting a result folder from the server (requires a security password to prevent accidental deletions). |

The filename parsing system (`parse_standard_filename` and `parse_ditg_filename` in `app.py`) is a key piece, enabling the GUI to automatically categorize and caption data according to:
*   Controller (ONOS, Ryu, ODL)
*   Topology (Mesh, 3-tier)
*   Mode (Proactive, Reactive, NN)
*   Metric (Latency, Throughput, RTT)
*   Test Scenario (Baseline, Malformed, REST, DoS)

## 📂 Project Structure

*   `Tool/benchmark.py`: **The main orchestrator.** Coordinates the entire workflow.
*   `Tool/xenorchestra.py`: Integration module with Xen Orchestra for automatic Mininet VM management.
*   `Mininet/mininet_server.py`: gRPC server running on the Mininet VM executing received commands.
*   `Tool/mininet_control.proto`: The formal definition of the gRPC API between the orchestrator and the Mininet server.
*   `gui/backend/app.py`: The Flask application serving the graphical result analysis interface.
*   `Tool/faultload.py`: Fault injection engine (REST Fuzzing and Malformed Packets).
*   `Tool/attackload.py`: Module for launching Denial of Service (DoS) attacks.
*   `Tool/mimic_cbench.py`: Tool for controller performance benchmarking.
*   `Tool/run.py`: Helper script with functions to manage SDN controllers via SSH and Docker.

## 🛠️ Prerequisites

*   Python 3.x
*   API access to Xen Orchestra.
*   Pre-configured VMs (for the Controller and as a template for Mininet).
*   Docker installed on the Controller VM.

## 📄 License

This project uses components under the CeCILL V2 and GNU GPLv3 licenses. See the `sourcesonoff` folder for more details.