import argparse
import time
from model_cache import ModelCache
from datetime import datetime

def format_size(size_bytes):
    if size_bytes is None:
        return "N/A"
    return f"{size_bytes / (1024 * 1024):.2f} MB"

def list_cache(host=None, model=None):
    cache = ModelCache()
    entries = cache.get_all_entries()

    if host:
        entries = [e for e in entries if host in e[0]]
    if model:
        entries = [e for e in entries if model in e[1]]

    if not entries:
        print("No cache entries found.")
        return

    print(f"{'Host':<40} {'Model':<30} {'VRAM Size':<15} {'Last Updated'}")
    print("-" * 100)
    for host_url, model_name, size_vram, last_updated in entries:
        dt = datetime.fromtimestamp(last_updated).strftime('%Y-%m-%d %H:%M:%S')
        print(f"{host_url:<40} {model_name:<30} {format_size(size_vram):<15} {dt}")

def clear_cache():
    cache = ModelCache()
    cache.clear()
    print("Cache cleared.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ollama Proxy Cache Management Tool")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    list_parser = subparsers.add_parser("list", help="List cache entries")
    list_parser.add_argument("--host", help="Filter by host URL")
    list_parser.add_argument("--model", help="Filter by model name")

    clear_parser = subparsers.add_parser("clear", help="Clear all cache entries")

    args = parser.parse_args()

    if args.command == "list":
        list_cache(args.host, args.model)
    elif args.command == "clear":
        confirm = input("Are you sure you want to clear the cache? (y/N): ")
        if confirm.lower() == 'y':
            clear_cache()
    else:
        parser.print_help()
