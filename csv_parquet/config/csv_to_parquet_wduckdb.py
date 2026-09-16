#!/usr/bin/env python3

import os
import sys
import pyarrow as pa
import pyarrow.csv as pv
import pyarrow.parquet as pq


def csv_to_parquet(
    input_csv,
    output_parquet,
    delimiter=",",
    quotechar='"',
    encoding="utf-8",
    compression="snappy",
    doublequote=True,
    chunk_size=1024 * 1024
):
    """
    Robust CSV -> Parquet converter using PyArrow streaming.
    Good for very large CSV files.
    """

    print(f"Reading: {input_csv}")
    print(f"Writing: {output_parquet}")

    read_options = pv.ReadOptions(
        block_size=chunk_size,
        encoding=encoding,
        use_threads=True
    )

    parse_options = pv.ParseOptions(
        delimiter=delimiter,
        quote_char=quotechar,
        double_quote=True,
        newlines_in_values=True
    )

    convert_options = pv.ConvertOptions(
        strings_can_be_null=True
    )

    reader = pv.open_csv(
        input_csv,
        read_options=read_options,
        parse_options=parse_options,
        convert_options=convert_options
    )

    writer = None
    total_rows = 0

    try:
        for batch_id, batch in enumerate(reader):

            table = pa.Table.from_batches([batch])

            if writer is None:
                writer = pq.ParquetWriter(
                    output_parquet,
                    table.schema,
                    compression=compression
                )

            writer.write_table(table)

            total_rows += table.num_rows

            print(
                f"Batch {batch_id + 1} | "
                f"Rows: {table.num_rows} | "
                f"Total: {total_rows}"
            )

    finally:
        if writer:
            writer.close()

    print("Finished successfully!")
    print(f"Total rows written: {total_rows}")


def main():

    if len(sys.argv) != 3:
        print(
            f"Usage:\n"
            f"python3 {sys.argv[0]} input.csv output.parquet"
        )
        sys.exit(1)

    input_csv = sys.argv[1]
    output_parquet = sys.argv[2]

    if not os.path.exists(input_csv):
        print(f"Input file not found: {input_csv}")
        sys.exit(1)

    csv_to_parquet(
        input_csv=input_csv,
        output_parquet=output_parquet,
        delimiter=",",
        quotechar='"',
        compression="snappy"
    )


if __name__ == "__main__":
    main()
