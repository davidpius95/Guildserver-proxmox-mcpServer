import argparse
from .templates import load_template_config, render_prompt


def main() -> None:
    parser = argparse.ArgumentParser(description="Render MCP natural-language prompt from template")
    parser.add_argument("tool", help="Template key (e.g., create_vm, get_vms)")
    parser.add_argument("--config", default="config/mcp_integration.yaml", help="Path to integration YAML")
    parser.add_argument("--set", action="append", default=[], help="Set param: key=value (repeat)")
    args = parser.parse_args()

    cfg = load_template_config(args.config)
    params = {}
    # Parse key=value pairs
    for item in args.set:
        if "=" in item:
            k, v = item.split("=", 1)
            params[k] = v

    prompt = render_prompt(args.tool, params, cfg)
    print(prompt)


if __name__ == "__main__":
    main()


