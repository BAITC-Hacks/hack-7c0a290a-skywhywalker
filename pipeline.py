"""One reproducible command for the three HackAlem CSV deliverables."""
import argparse
from pathlib import Path
from time import perf_counter
from backend.datasets import load_dataset, load_official
from backend.analysis import Analysis
from backend.submission import write_outputs, frames_for_analysis


def main():
    parser = argparse.ArgumentParser(description='Рассчитать роли, группы и очередь проверки')
    parser.add_argument('--data',type=Path,default=Path('data/official'))
    parser.add_argument('--out',type=Path,default=Path('out'))
    args = parser.parse_args()
    started = perf_counter()
    df = load_dataset(args.data.read_bytes(),args.data.name) if args.data.is_file() else load_official(args.data)
    analysis = Analysis(df,args.data.name)
    write_outputs(analysis,args.out)
    frames = frames_for_analysis(analysis)
    print(f"OK: {len(analysis.nodes)} nodes, {analysis.graph.number_of_edges()} pairs, {len(df)} transactions")
    print(f"CSV: {len(frames['nodes_roles.csv'])} roles, {len(frames['clusters.csv'])} clusters, {len(frames['top_nodes.csv'])} top nodes")
    print(f"Completed in {perf_counter()-started:.2f}s. Output: {args.out.resolve()}")


if __name__ == '__main__':
    main()
