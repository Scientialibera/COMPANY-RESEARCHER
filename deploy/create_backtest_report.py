"""
Create a Fabric Power BI report (PBIR-Legacy format) showing Backtest Actual vs Predicted,
bound to the IBP Forecast Model semantic model.

Run:  python deploy/create_backtest_report.py
"""

import base64, json, subprocess, requests, sys, uuid, time

# ── Fabric IDs ───────────────────────────────────────────────────────────────
WORKSPACE_ID      = "25c5ea03-0780-4dae-a9a0-11de3cccb0d9"
SEMANTIC_MODEL_ID = "e5f9030e-3901-408c-9d6c-47a97112dfa1"
FOLDER_ID         = "730d8b2a-9177-4a26-9deb-d695cc341f84"
REPORT_NAME       = "IBP Backtest - Actual vs Predicted"

API_BASE = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}"
ENTITY   = "Backtest Predictions"
SRC      = "b"

# ── Helpers ──────────────────────────────────────────────────────────────────

def get_token() -> str:
    r = subprocess.run(
        "az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv",
        capture_output=True, text=True, check=True, shell=True,
    )
    return r.stdout.strip()


def b64(obj) -> str:
    raw = json.dumps(obj, indent=2) if isinstance(obj, dict) else obj
    return base64.b64encode(raw.encode()).decode()


def col_expr(prop: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Source": SRC}}, "Property": prop}}


def msr_expr(prop: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Source": SRC}}, "Property": prop}}


def col_select(prop: str) -> dict:
    return {**col_expr(prop), "Name": f"{ENTITY}.{prop}"}


def msr_select(prop: str) -> dict:
    return {**msr_expr(prop), "Name": f"{ENTITY}.{prop}"}


def agg_select(prop: str, func: int, alias: str) -> dict:
    return {
        "Aggregation": {"Expression": col_expr(prop), "Function": func},
        "Name": alias,
    }


# ── Visual container builder ─────────────────────────────────────────────────

def visual_container(name, x, y, z, w, h, visual_type,
                     projections, selects, order_by=None, objects=None):
    cfg = {
        "name": name,
        "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h}}],
        "singleVisual": {
            "visualType": visual_type,
            "projections": projections,
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": SRC, "Entity": ENTITY, "Type": 0}],
                "Select": selects,
            },
            "drillFilterOtherVisuals": True,
        },
    }
    if order_by:
        cfg["singleVisual"]["prototypeQuery"]["OrderBy"] = order_by
    if objects:
        cfg["singleVisual"]["objects"] = objects

    return {
        "config": json.dumps(cfg),
        "filters": "[]",
        "height": float(h),
        "width": float(w),
        "x": float(x),
        "y": float(y),
        "z": z,
    }


# ── Layout ───────────────────────────────────────────────────────────────────
# Row 1: Slicers   y=20  h=50
# Row 2: Cards     y=85  h=75  (taller so labels aren't clipped)
# Row 3: Line      y=175 h=230
# Row 4: Table     y=420 h=280

SLICER_Y = 15;  SLICER_H = 50
CARD_Y   = 85;  CARD_H   = 75
CHART_Y  = 185; CHART_H  = 220
TABLE_Y  = 425; TABLE_H  = 275

DROPDOWN = {"data": [{"properties": {"mode": {"expr": {"Literal": {"Value": "'Dropdown'"}}}}}]}

# ── Row 1: Slicers ───────────────────────────────────────────────────────────

slicer_model = visual_container(
    name="vis_slicer_model", x=20, y=SLICER_Y, z=0, w=250, h=SLICER_H,
    visual_type="slicer",
    projections={"Values": [{"queryRef": f"{ENTITY}.model_type"}]},
    selects=[col_select("model_type")],
    objects=DROPDOWN,
)

slicer_plant = visual_container(
    name="vis_slicer_plant", x=285, y=SLICER_Y, z=10, w=250, h=SLICER_H,
    visual_type="slicer",
    projections={"Values": [{"queryRef": f"{ENTITY}.plant_id"}]},
    selects=[col_select("plant_id")],
    objects=DROPDOWN,
)

slicer_sku = visual_container(
    name="vis_slicer_sku", x=550, y=SLICER_Y, z=20, w=250, h=SLICER_H,
    visual_type="slicer",
    projections={"Values": [{"queryRef": f"{ENTITY}.sku_id"}]},
    selects=[col_select("sku_id")],
    objects=DROPDOWN,
)

# ── Row 2: Metric cards ─────────────────────────────────────────────────────

card_mape = visual_container(
    name="vis_card_mape", x=20, y=CARD_Y, z=500, w=230, h=CARD_H,
    visual_type="card",
    projections={"Values": [{"queryRef": f"{ENTITY}.Backtest MAPE %"}]},
    selects=[msr_select("Backtest MAPE %")],
)

AVG_ABS = "Avg.abs_error"
card_avg_abs = visual_container(
    name="vis_card_avgabs", x=265, y=CARD_Y, z=510, w=230, h=CARD_H,
    visual_type="card",
    projections={"Values": [{"queryRef": AVG_ABS}]},
    selects=[agg_select("abs_error", 1, AVG_ABS)],
)

AVG_PCT = "Avg.pct_error"
card_avg_pct = visual_container(
    name="vis_card_avgpct", x=510, y=CARD_Y, z=520, w=230, h=CARD_H,
    visual_type="card",
    projections={"Values": [{"queryRef": AVG_PCT}]},
    selects=[agg_select("pct_error", 1, AVG_PCT)],
)

card_actual = visual_container(
    name="vis_card_actual", x=755, y=CARD_Y, z=530, w=230, h=CARD_H,
    visual_type="card",
    projections={"Values": [{"queryRef": f"{ENTITY}.Total Actual"}]},
    selects=[msr_select("Total Actual")],
)

card_pred = visual_container(
    name="vis_card_pred", x=1000, y=CARD_Y, z=540, w=230, h=CARD_H,
    visual_type="card",
    projections={"Values": [{"queryRef": f"{ENTITY}.Total Predicted"}]},
    selects=[msr_select("Total Predicted")],
)

# ── Row 3: Line chart ────────────────────────────────────────────────────────

line_chart = visual_container(
    name="vis_linechart", x=20, y=CHART_Y, z=1000, w=1240, h=CHART_H,
    visual_type="lineChart",
    projections={
        "Category": [{"queryRef": f"{ENTITY}.period"}],
        "Y": [
            {"queryRef": f"{ENTITY}.Total Actual"},
            {"queryRef": f"{ENTITY}.Total Predicted"},
        ],
    },
    selects=[col_select("period"), msr_select("Total Actual"), msr_select("Total Predicted")],
    order_by=[{"Direction": 1, "Expression": col_expr("period")}],
)

# ── Row 4: Detail table ──────────────────────────────────────────────────────

TABLE_COLS = ["period", "plant_id", "sku_id", "model_type",
              "actual", "predicted", "error", "abs_error", "pct_error"]

detail_table = visual_container(
    name="vis_detail_table", x=20, y=TABLE_Y, z=2000, w=1240, h=TABLE_H,
    visual_type="tableEx",
    projections={"Values": [{"queryRef": f"{ENTITY}.{c}"} for c in TABLE_COLS]},
    selects=[col_select(c) for c in TABLE_COLS],
    order_by=[{"Direction": 1, "Expression": col_expr("period")}],
)

# ── Assemble PBIR-Legacy report.json ─────────────────────────────────────────

report_config = {
    "version": "5.68",
    "themeCollection": {
        "baseTheme": {
            "name": "CY25SU11",
            "version": {"visual": "2.4.0", "report": "3.0.0", "page": "2.3.0"},
            "type": 2,
        }
    },
    "activeSectionIndex": 0,
    "defaultDrillFilterOtherVisuals": True,
    "settings": {
        "useNewFilterPaneExperience": True,
        "allowChangeFilterTypes": True,
        "useStylableVisualContainerHeader": True,
        "useDefaultAggregateDisplayName": True,
        "useEnhancedTooltips": True,
    },
}

report_json = {
    "config": json.dumps(report_config),
    "layoutOptimization": 0,
    "resourcePackages": [{
        "resourcePackage": {
            "disabled": False,
            "items": [{"name": "CY25SU11", "path": "BaseThemes/CY25SU11.json", "type": 202}],
            "name": "SharedResources",
            "type": 2,
        }
    }],
    "sections": [{
        "config": "{}",
        "displayName": "Backtest: Actual vs Predicted",
        "displayOption": 1,
        "filters": "[]",
        "height": 720.00,
        "width": 1280.00,
        "name": "backtestpage01",
        "visualContainers": [
            slicer_model, slicer_plant, slicer_sku,
            card_mape, card_avg_abs, card_avg_pct, card_actual, card_pred,
            line_chart, detail_table,
        ],
    }],
}

definition_pbir = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
    "version": "4.0",
    "datasetReference": {
        "byConnection": {"connectionString": f"semanticmodelid={SEMANTIC_MODEL_ID}"}
    },
}

platform_json = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "Report", "displayName": REPORT_NAME},
    "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
}

parts = [
    {"path": "report.json",     "payload": b64(report_json),     "payloadType": "InlineBase64"},
    {"path": "definition.pbir", "payload": b64(definition_pbir), "payloadType": "InlineBase64"},
    {"path": ".platform",       "payload": b64(platform_json),   "payloadType": "InlineBase64"},
]

# ── Deploy ────────────────────────────────────────────────────────────────────

def main():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    body = {
        "displayName": REPORT_NAME,
        "description": "Backtest analysis: actual vs predicted by model type with error metrics, sorted ascending by period.",
        "folderId": FOLDER_ID,
        "definition": {"parts": parts},
    }

    print(f"Creating report '{REPORT_NAME}' ...")
    print(f"  Visuals: 3 slicers (model, plant, sku) | 5 cards | line chart | table")

    resp = requests.post(f"{API_BASE}/reports", headers=headers, json=body)

    if resp.status_code in (200, 201):
        data = resp.json()
        rid = data.get("id", "")
        print(f"\nReport created!\n  URL: https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{rid}")
        return

    if resp.status_code == 202:
        op_id = resp.headers.get("x-ms-operation-id", "")
        print(f"\nPolling operation {op_id} ...")
        for i in range(30):
            time.sleep(3)
            poll = requests.get(f"https://api.fabric.microsoft.com/v1/operations/{op_id}", headers=headers)
            if poll.status_code != 200:
                continue
            status = poll.json().get("status", "")
            print(f"  [{3*(i+1):>3}s] {status}")
            if status == "Succeeded":
                result = requests.get(f"https://api.fabric.microsoft.com/v1/operations/{op_id}/result", headers=headers)
                if result.status_code == 200:
                    rid = result.json().get("id", "")
                    print(f"\nReport created!\n  URL: https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{rid}")
                return
            if status == "Failed":
                print(f"\nFailed:\n{poll.text}")
                sys.exit(1)
        print("Timed out.")
        sys.exit(1)

    print(f"\nHTTP {resp.status_code}:\n{resp.text}")
    sys.exit(1)


if __name__ == "__main__":
    main()
