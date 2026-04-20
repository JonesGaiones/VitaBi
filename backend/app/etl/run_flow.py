"""
Entry point usado pelos cron jobs do Antigravity.
Uso: python -m app.etl.run_flow <flow_name> [args...]
"""
import asyncio
import sys

from app.etl import flows


FLOW_MAP = {
    "qb_extract_flow": flows.qb_extract_flow,
    "transform_flow": flows.transform_flow,
    "mv_refresh_flow": flows.mv_refresh_flow,
    "insights_flow": flows.insights_flow,
    "churn_flow": flows.churn_flow,
    "de_para_apply_flow": flows.de_para_apply_flow,
    "full_pipeline": flows.full_pipeline,
}


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: python -m app.etl.run_flow <flow_name>")
        print(f"Available flows: {', '.join(FLOW_MAP)}")
        sys.exit(1)

    flow_name = sys.argv[1]
    if flow_name not in FLOW_MAP:
        print(f"Unknown flow: {flow_name}")
        sys.exit(1)

    flow_fn = FLOW_MAP[flow_name]
    args = sys.argv[2:]

    result = asyncio.run(flow_fn(*args))
    print(result)


if __name__ == "__main__":
    main()
