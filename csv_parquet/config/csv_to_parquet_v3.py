from pathlib import Path
import yaml
import pandas as pd
import duckdb

def load_datasets_config(config_path: str) -> list[dict]:
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config["datasets"]

def convert_dataset(dataset: dict) -> None:
    name = dataset["name"]
    input_path = Path(dataset["input_path"])
    output_path = Path(dataset["output_path"])
    opts = dataset.get("read_options", {})

    if not input_path.exists():
        print(f"[ERRO] Arquivo não encontrado: {input_path}")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Configurações de leitura (Fallbacks para o padrão SSMS)
    delim = opts.get("delim", ",")
    quote = opts.get("quote", '"')
    # No Python/Pandas, o padrão para exportação SQL ANSI é cp1252
    encoding = opts.get("encoding", "cp1252") 

    print(f"\n--- Processando: {name} ---")
    print(f"Lendo arquivo para memória RAM...")

    try:
        # 1. Leitura robusta com Pandas
        # dtype=str e low_memory=False garantem que o parser não tente "adivinhar" e errar
        df = pd.read_csv(
            input_path,
            sep=delim,
            quotechar=quote,
            encoding=encoding,
            dtype=str,
            header=0 if opts.get("header", True) else None,
            engine='python',            # Motor C é o mais rápido e estável
            on_bad_lines=lambda x: x[:-1] # Tenta truncar o campo extra se possível
            #low_memory=False      # Carrega o arquivo todo de uma vez (aproveita sua RAM)
            #on_bad_lines='error'   # Trava se o CSV estiver malformado (Garante integridade)
        )

        total_rows = len(df)
        print(f"Sucesso na leitura: {total_rows:,} linhas carregadas.")

        # 2. Exportação via DuckDB (Integração nativa com Pandas)
        print(f"Convertendo para Parquet...")
        con = duckdb.connect()
        
        # O DuckDB consegue ler o objeto 'df' diretamente do escopo local
        con.execute(f"""
            COPY (SELECT * FROM df) 
            TO '{str(output_path)}' 
            (FORMAT PARQUET, COMPRESSION 'ZSTD')
        """)
        
        # 3. Validação
        count_parquet = con.execute(f"SELECT count(*) FROM '{str(output_path)}'").fetchone()[0]
        con.close()

        print(f"[OK] {name} finalizado.")
        print(f"      Linhas no DataFrame: {total_rows:,}")
        print(f"      Linhas no Parquet:   {count_parquet:,}")

        if total_rows != count_parquet:
            print("      [AVISO] Mismatch detectado entre DataFrame e Parquet!")

    except Exception as e:
        print(f"[FALHA] Erro crítico em {name}: {e}")

def main():
    config_path = Path("../config/datasets.yaml")
    if not config_path.exists():
        print(f"Configuração não encontrada em: {config_path}")
        return

    datasets = load_datasets_config(str(config_path))
    for dataset in datasets:
        convert_dataset(dataset)

if __name__ == "__main__":
    main()
