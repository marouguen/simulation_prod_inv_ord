from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# File paths
MACHINES_CSV = "machines.csv"
ORDERS_CSV = "orders.csv"
INVENTORY_CSV = "inventory.csv"

def load_csv(file_path):
    """Load CSV file."""
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        return df
    return pd.DataFrame()

def parse_datetime(datetime_string):
    """Parse datetime string into a datetime object."""
    formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M"]
    for fmt in formats:
        try:
            return datetime.strptime(datetime_string, fmt)
        except ValueError:
            continue
    raise ValueError(f"Time data '{datetime_string}' does not match any known format.")

@app.route("/", methods=["GET", "POST"])
def index():
    machines_data = load_csv(MACHINES_CSV).to_dict(orient="records")
    if request.method == "POST":
        plans = []
        for machine in machines_data:
            name = machine["name"]
            plans.append({
                "name": name,
                "start_datetime": request.form[f"{name}_start_datetime"],
                "shifts_per_day": int(request.form[f"{name}_shifts_per_day"]),
                "hours_per_shift": int(request.form[f"{name}_hours_per_shift"]),
                "employees_available": int(request.form[f"{name}_employees_available"]),
            })

        # Handle file uploads
        if "inventory_file" in request.files:
            inventory_file = request.files["inventory_file"]
            if inventory_file:
                inventory_file.save(INVENTORY_CSV)

        if "orders_file" in request.files:
            orders_file = request.files["orders_file"]
            if orders_file:
                orders_file.save(ORDERS_CSV)

        return simulate(plans)

    return render_template("index.html", machines_data=machines_data)

@app.route("/simulate", methods=["POST", "GET"])
def simulate(plans=None):
    if plans is None:
        return redirect(url_for("index"))

    machines_data = load_csv(MACHINES_CSV)
    orders_data = load_csv(ORDERS_CSV)
    inventory_data = load_csv(INVENTORY_CSV)

    total_consumption = {}
    stockouts = {}
    inventory_status = {}
    machine_results = []
    orders_results = []

    for index, row in inventory_data.iterrows():
        total_consumption[row["material_name"]] = 0
        stockouts[row["material_name"]] = 0

    for plan in plans:
        machine_params = machines_data[machines_data["name"] == plan["name"]].iloc[0]
        hours_available = plan["shifts_per_day"] * plan["hours_per_shift"]
        production_rate = machine_params["rate_kg_h"]
        scrap_rate = machine_params["scrap"] / 100
        downtime_rate = machine_params["downtime"] / 100
        material_needed = machine_params["material_kg_unit"]
        employees_needed = machine_params["employees_needed_shift"]

        if plan["employees_available"] < employees_needed:
            machine_results.append({
                "machine": plan["name"],
                "status": "Not enough employees",
                "production": 0,
                "material_consumed": 0,
                "used_capacity": 0,
                "downtime_rate": downtime_rate,
                "scrap_rate": scrap_rate,
            })
            continue

        potential_production =  production_rate
        actual_production = potential_production * (1 - scrap_rate)
        material_used = actual_production * material_needed

        total_consumption[machine_params["material_name"]] += material_used

        machine_results.append({
            "machine": plan["name"],
            "status": "Simulated",
            "production": potential_production,
            "material_consumed": material_used,
            "used_capacity": (actual_production / potential_production) * 100,
            "downtime_rate": downtime_rate,
            "scrap_rate": scrap_rate,
        })

    for material, consumed in total_consumption.items():
        row = inventory_data[inventory_data["material_name"] == material].iloc[0]
        initial_level = row["initial_level_kg"]
        reorder_quantity = row["reorder_quantity_kg"]
        if consumed > initial_level:
            stockouts[material] += 1
            final_level = initial_level - consumed + reorder_quantity
        else:
            final_level = initial_level - consumed
        inventory_status[material] = {
            "initial": initial_level,
            "consumed": consumed,
            "reorder_quantity": reorder_quantity if final_level > initial_level else 0,
            "final": final_level,
            "stockouts": stockouts[material],
        }

    for index, order in orders_data.iterrows():
        entry_date = parse_datetime(order["entry_date"])
        due_date = entry_date + timedelta(hours=order["agreed_lead_time"])
        order_size = order["order_size"]
        material_name = order["material_name"]

        completed_quantity = min(order_size, total_consumption.get(material_name, 0))
        total_consumption[material_name] -= completed_quantity

        orders_results.append({
            "order_id": order["order_id"],
            "status": "Completed" if completed_quantity == order_size else "Pending",
            "completed_quantity": completed_quantity,
            "entry_date": entry_date.strftime("%Y-%m-%d %H:%M"),
            "due_date": due_date.strftime("%Y-%m-%d %H:%M"),
            "on_time": "Yes" if completed_quantity == order_size else "No",
        })

    return render_template(
        "results.html",
        machines=machine_results,
        inventory=inventory_status,
        orders=orders_results,
    )

if __name__ == "__main__":
    app.run(debug=True)
